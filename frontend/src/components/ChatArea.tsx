import { useEffect, useRef, useState } from "react"
import PromptInput from "@cloudscape-design/components/prompt-input"
import SpaceBetween from "@cloudscape-design/components/space-between"
import Button from "@cloudscape-design/components/button"
import Box from "@cloudscape-design/components/box"
import Header from "@cloudscape-design/components/header"
import ChatBubble from "@cloudscape-design/chat-components/chat-bubble"
import Avatar from "@cloudscape-design/chat-components/avatar"
import LoadingBar from "@cloudscape-design/chat-components/loading-bar"
import type { ChatMessage } from "../types"
import Markdown from "./Markdown"

export interface AttachedImage {
  data: string
  format: string
  name: string
}

interface ChatAreaProps {
  title: string
  messages: ChatMessage[]
  streaming: string
  loading: boolean
  solutionReady: boolean
  artifactsOpen: boolean
  attachments?: Record<number, string>
  onToggleArtifacts: () => void
  onSend: (text: string, image?: AttachedImage) => void
}

export default function ChatArea({
  title,
  messages,
  streaming,
  loading,
  solutionReady,
  artifactsOpen,
  attachments,
  onToggleArtifacts,
  onSend,
}: ChatAreaProps) {
  const [value, setValue] = useState("")
  const [image, setImage] = useState<AttachedImage | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, streaming, loading])

  function submit() {
    const text = value.trim()
    if ((!text && !image) || loading) return
    setValue("")
    onSend(text || "Analyze this architecture diagram.", image ?? undefined)
    setImage(null)
  }

  async function onFile(file?: File) {
    if (!file) return
    const dataUrl: string = await new Promise((res, rej) => {
      const r = new FileReader()
      r.onload = () => res(r.result as string)
      r.onerror = rej
      r.readAsDataURL(file)
    })
    const format = (file.type.split("/")[1] || "png").replace("jpg", "jpeg")
    setImage({ data: dataUrl, format, name: file.name })
  }

  return (
    <div className="dg-chat-col">
      <div className="dg-chat-header">
        <Header
          variant="h2"
          actions={
            <Button
              iconName="gen-ai"
              variant={artifactsOpen ? "primary" : "normal"}
              disabled={!solutionReady}
              onClick={onToggleArtifacts}
            >
              Artifacts
            </Button>
          }
        >
          {title}
        </Header>
      </div>

      <div className="dg-chat-scroll dg-chat-grow">
        <SpaceBetween size="m">
          {messages.length === 0 && !loading && (
            <ChatBubble
              type="incoming"
              ariaLabel="DevGenius"
              avatar={<Avatar ariaLabel="DevGenius" tooltipText="DevGenius" color="gen-ai" iconName="gen-ai" />}
            >
              <Markdown>
                {
                  "Welcome to **DevGenius**. Tell me what you want to build on AWS and I'll ask a few questions, then design a complete, deployable solution grounded in the latest AWS guidance. You can also attach an architecture diagram to analyze an existing design."
                }
              </Markdown>
            </ChatBubble>
          )}
          {messages.map((m, i) => (
            <ChatBubble
              key={i}
              type={m.role === "user" ? "outgoing" : "incoming"}
              ariaLabel={m.role === "user" ? "You" : "DevGenius"}
              avatar={
                m.role === "user" ? (
                  <Avatar ariaLabel="You" tooltipText="You" initials="You" />
                ) : (
                  <Avatar ariaLabel="DevGenius" tooltipText="DevGenius" color="gen-ai" iconName="gen-ai" />
                )
              }
            >
              {m.role === "user" ? (
                <SpaceBetween size="xs">
                  {attachments?.[i] && (
                    <img src={attachments[i]} alt="attachment" className="dg-msg-img" />
                  )}
                  <Box>{m.content}</Box>
                </SpaceBetween>
              ) : (
                <Markdown>{m.content}</Markdown>
              )}
            </ChatBubble>
          ))}

          {loading && (
            <ChatBubble
              type="incoming"
              ariaLabel="DevGenius is thinking"
              avatar={<Avatar ariaLabel="DevGenius" color="gen-ai" iconName="gen-ai" loading />}
            >
              {streaming ? <Markdown>{streaming}</Markdown> : <Box>Researching and composing a grounded answer...</Box>}
              <LoadingBar variant="gen-ai" />
            </ChatBubble>
          )}
          <div ref={endRef} />
        </SpaceBetween>
      </div>

      <div className="dg-chat-input">
        <SpaceBetween size="xs">
          {image && (
            <div className="dg-attach-preview">
              <img src={image.data} alt={image.name} className="dg-attach-thumb" />
              <span className="dg-attach-name">{image.name}</span>
              <Button
                variant="icon"
                iconName="close"
                ariaLabel="Remove attachment"
                onClick={() => setImage(null)}
              />
            </div>
          )}
          <PromptInput
            value={value}
            onChange={({ detail }) => setValue(detail.value)}
            onAction={submit}
            disabled={loading}
            actionButtonAriaLabel="Send"
            actionButtonIconName="send"
            placeholder="Describe what you want to build, or attach an architecture image..."
            maxRows={6}
            secondaryActions={
              <Box padding={{ left: "xxs", top: "xxs" }}>
                <Button
                  iconName="upload"
                  variant="icon"
                  ariaLabel="Attach an architecture image"
                  onClick={() => fileRef.current?.click()}
                />
              </Box>
            }
          />
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/gif,image/webp"
            style={{ display: "none" }}
            onChange={(e) => onFile(e.target.files?.[0])}
          />
        </SpaceBetween>
      </div>
    </div>
  )
}
