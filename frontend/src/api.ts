/**
 * Typed client for the DevGenius backend.
 *
 * The backend Lambda Function URL is public (authType NONE); we authenticate by
 * sending the Cognito access token as a bearer credential, which the Lambda
 * validates on every request.
 */
import { fetchAuthSession } from "aws-amplify/auth"
import { getConfig } from "./config"
import type {
  ChatMessage,
  ChatResponse,
  ArtifactKey,
  GenerateResponse,
  ConversationSummary,
  LoadedConversation,
} from "./types"

async function idToken(): Promise<string> {
  const session = await fetchAuthSession()
  const token = session.tokens?.idToken?.toString()
  if (!token) throw new Error("Not signed in - please sign in again.")
  return token
}

async function request<T>(pathSuffix: string, method: string, payload?: Record<string, unknown>): Promise<T> {
  const token = await idToken()
  const res = await fetch(getConfig().apiUrl + pathSuffix, {
    method,
    headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
    body: payload ? JSON.stringify(payload) : undefined,
  })
  const text = await res.text()
  if (!res.ok) {
    let message = text
    try {
      message = JSON.parse(text).error ?? text
    } catch {
      /* keep raw text */
    }
    throw new Error(message || `Request failed (${res.status})`)
  }
  return (text ? JSON.parse(text) : {}) as T
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/**
 * POST /invoke. Quick actions return their result directly; chat/generate
 * return a jobId that we poll until the async work completes.
 */
async function post<T>(payload: Record<string, unknown>, onPartial?: (t: string) => void): Promise<T> {
  const res = await request<{ jobId?: string } & T>("/invoke", "POST", payload)
  if (res && (res as { jobId?: string }).jobId) {
    return pollJob<T>((res as { jobId: string }).jobId, onPartial)
  }
  return res as T
}

async function pollJob<T>(jobId: string, onPartial?: (t: string) => void): Promise<T> {
  // Up to ~11 minutes; long generations (docs, diagrams) with live web search can
  // run several minutes. Transient poll failures are tolerated so a single blip
  // doesn't fail the whole request. Partial output is streamed via onPartial.
  let transientErrors = 0
  for (let i = 0; i < 330; i++) {
    await sleep(2000)
    let job: { status: string; result?: T; error?: string; partial?: string }
    try {
      job = await request(`/job/${jobId}`, "GET")
      transientErrors = 0
    } catch (e) {
      if (++transientErrors > 5) throw e // give up after repeated network/5xx blips
      continue
    }
    if (job.partial && onPartial) onPartial(job.partial)
    if (job.status === "done") return job.result as T
    if (job.status === "error") throw new Error(job.error || "Generation failed")
  }
  throw new Error("Timed out waiting for the result. Please try again.")
}

export interface UserContext {
  userEmail: string
  userName: string
}

export const api = {
  startSession(conversationId: string, user: UserContext) {
    return post<{ ok: boolean }>({ action: "session", conversationId, ...user })
  },

  chat(
    params: {
      conversationId: string
      messages: ChatMessage[]
      message: string
      image?: string
      imageFormat?: string
      mode: "build" | "analyze"
      user: UserContext
    },
    onPartial?: (t: string) => void
  ) {
    return post<ChatResponse>(
      {
        action: "chat",
        conversationId: params.conversationId,
        messages: params.messages,
        message: params.message,
        image: params.image,
        imageFormat: params.imageFormat,
        mode: params.mode,
        ...params.user,
      },
      onPartial
    )
  },

  generate(
    params: {
      conversationId: string
      artifact: ArtifactKey
      messages: ChatMessage[]
      user: UserContext
    },
    onPartial?: (t: string) => void
  ) {
    return post<GenerateResponse>(
      {
        action: "generate",
        conversationId: params.conversationId,
        artifact: params.artifact,
        messages: params.messages,
        ...params.user,
      },
      onPartial
    )
  },

  bundle(conversationId: string) {
    return post<{ downloadUrl: string }>({ action: "bundle", conversationId })
  },

  listConversations() {
    return post<{ conversations: ConversationSummary[] }>({ action: "listConversations" })
  },

  loadConversation(conversationId: string) {
    return post<LoadedConversation>({ action: "loadConversation", conversationId })
  },

  deleteConversation(conversationId: string) {
    return post<{ ok: boolean }>({ action: "deleteConversation", conversationId })
  },

  feedback(params: {
    conversationId: string
    sentiment: "up" | "down"
    explanation?: string
    response?: string
    useCase?: string
  }) {
    return post<{ ok: boolean }>({ action: "feedback", ...params })
  },
}
