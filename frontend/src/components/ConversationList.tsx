import Box from "@cloudscape-design/components/box"
import Button from "@cloudscape-design/components/button"
import SpaceBetween from "@cloudscape-design/components/space-between"
import Spinner from "@cloudscape-design/components/spinner"
import type { ConversationSummary } from "../types"

interface ConversationListProps {
  conversations: ConversationSummary[]
  activeId: string
  loading: boolean
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (conversation: ConversationSummary) => void
}

export default function ConversationList({
  conversations,
  activeId,
  loading,
  onSelect,
  onNew,
  onDelete,
}: ConversationListProps) {
  return (
    <div className="dg-conv-list">
      <Box padding="s">
        <Button iconName="add-plus" variant="primary" fullWidth onClick={onNew}>
          New chat
        </Button>
      </Box>
      <Box padding={{ horizontal: "s", bottom: "xxs" }} fontSize="body-s" color="text-body-secondary">
        Conversations
      </Box>
      {loading ? (
        <Box padding="s">
          <Spinner /> Loading...
        </Box>
      ) : conversations.length === 0 ? (
        <Box padding="s" color="text-body-secondary" fontSize="body-s">
          No conversations yet.
        </Box>
      ) : (
        <SpaceBetween size="xxs">
          {conversations.map((c) => (
            <div
              key={c.conversationId}
              className={`dg-conv-item${c.conversationId === activeId ? " dg-conv-active" : ""}`}
              onClick={() => onSelect(c.conversationId)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onSelect(c.conversationId)}
              title={c.title}
            >
              <div className="dg-conv-main">
                <span className="dg-conv-title">{c.title || "Untitled"}</span>
                <span className="dg-conv-time">{c.updated?.slice(0, 10)}</span>
              </div>
              <span className="dg-conv-del" onClick={(e) => e.stopPropagation()}>
                <Button
                  variant="icon"
                  iconName="remove"
                  ariaLabel={`Delete conversation ${c.title}`}
                  onClick={() => onDelete(c)}
                />
              </span>
            </div>
          ))}
        </SpaceBetween>
      )}
    </div>
  )
}
