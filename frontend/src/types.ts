export type Role = "user" | "assistant"

export interface ChatMessage {
  role: Role
  content: string
}

export interface Citation {
  title: string
  url: string
}

export interface ChatResponse {
  assistant: string
  solutionReady: boolean
  citations: Citation[]
}

export type ArtifactKey =
  | "cost"
  | "architecture"
  | "cdk"
  | "cfn"
  | "terraform"
  | "documentation"

export interface GenerateResponse {
  artifact: ArtifactKey
  content: string
  citations: Citation[]
  diagramXml?: string
  templateUrl?: string
  launchStackUrl?: string
}

export interface ConversationSummary {
  conversationId: string
  title: string
  updated: string
}

export interface LoadedConversation {
  messages: ChatMessage[]
  artifacts: Partial<Record<ArtifactKey, GenerateResponse>>
  solutionReady: boolean
}
