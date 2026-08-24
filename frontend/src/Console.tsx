import { useCallback, useEffect, useMemo, useState } from "react"
import AppLayout from "@cloudscape-design/components/app-layout"
import SplitPanel from "@cloudscape-design/components/split-panel"
import Alert from "@cloudscape-design/components/alert"
import Modal from "@cloudscape-design/components/modal"
import Box from "@cloudscape-design/components/box"
import Button from "@cloudscape-design/components/button"
import SpaceBetween from "@cloudscape-design/components/space-between"
import type { ArtifactKey, ChatMessage, ConversationSummary } from "./types"
import { api } from "./api"
import ConversationList from "./components/ConversationList"
import ChatArea, { type AttachedImage } from "./components/ChatArea"
import ArtifactsView, { type ArtifactState, ARTIFACTS } from "./components/ArtifactsPanel"

const SPLIT_I18N = {
  preferencesTitle: "Split panel preferences",
  preferencesPositionLabel: "Position",
  preferencesPositionDescription: "Where to place the artifacts panel.",
  preferencesPositionSide: "Side",
  preferencesPositionBottom: "Bottom",
  preferencesConfirm: "Confirm",
  preferencesCancel: "Cancel",
  closeButtonAriaLabel: "Close artifacts",
  openButtonAriaLabel: "Open artifacts",
  resizeHandleAriaLabel: "Resize artifacts panel",
}

export default function Console({ email }: { email: string }) {
  const user = useMemo(() => ({ userEmail: email, userName: email.split("@")[0] || "user" }), [email])

  const [convId, setConvId] = useState<string>(() => crypto.randomUUID())
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [attachments, setAttachments] = useState<Record<number, string>>({})
  const [analyzeMode, setAnalyzeMode] = useState(false)
  const [streaming, setStreaming] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [solutionReady, setSolutionReady] = useState(false)

  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [listLoading, setListLoading] = useState(false)
  const [navOpen, setNavOpen] = useState(true)

  const [splitOpen, setSplitOpen] = useState(false)
  const [artifacts, setArtifacts] = useState<Partial<Record<ArtifactKey, ArtifactState>>>({})
  const [activeTab, setActiveTab] = useState<ArtifactKey>("cost")
  const [generatingAll, setGeneratingAll] = useState(false)
  const [bundling, setBundling] = useState(false)

  const [deleteTarget, setDeleteTarget] = useState<ConversationSummary | null>(null)
  const [deleting, setDeleting] = useState(false)

  const refreshList = useCallback(async () => {
    setListLoading(true)
    try {
      const { conversations } = await api.listConversations()
      setConversations(conversations)
    } catch {
      /* non-fatal */
    } finally {
      setListLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshList()
  }, [refreshList])

  function newChat() {
    setConvId(crypto.randomUUID())
    setMessages([])
    setAttachments({})
    setAnalyzeMode(false)
    setStreaming("")
    setSolutionReady(false)
    setArtifacts({})
    setSplitOpen(false)
    setError(null)
  }

  async function selectConversation(id: string) {
    if (id === convId) return
    setConvId(id)
    setMessages([])
    setAttachments({})
    setAnalyzeMode(false)
    setArtifacts({})
    setSplitOpen(false)
    setError(null)
    setLoading(true)
    try {
      const loaded = await api.loadConversation(id)
      setMessages(loaded.messages || [])
      setSolutionReady(loaded.solutionReady)
      const restored: Partial<Record<ArtifactKey, ArtifactState>> = {}
      for (const [key, result] of Object.entries(loaded.artifacts || {})) {
        restored[key as ArtifactKey] = { result }
      }
      setArtifacts(restored)
      const firstArtifact = ARTIFACTS.find((a) => restored[a.key])
      if (firstArtifact) setActiveTab(firstArtifact.key)
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
    } finally {
      setLoading(false)
    }
  }

  async function send(text: string, image?: AttachedImage) {
    const prior = messages
    const isFirst = prior.length === 0
    setError(null)
    setLoading(true)
    setStreaming("")
    setMessages([...prior, { role: "user", content: text }])
    // Keep the attached image for inline display only (never sent in the history).
    if (image) setAttachments((a) => ({ ...a, [prior.length]: image.data }))
    // Once an image is attached, the conversation stays in "analyze/refine" mode.
    const mode: "build" | "analyze" = image || analyzeMode ? "analyze" : "build"
    if (image) setAnalyzeMode(true)
    try {
      const res = await api.chat(
        {
          conversationId: convId,
          messages: prior,
          message: text,
          image: image?.data,
          imageFormat: image?.format,
          mode,
          user,
        },
        (partial) => setStreaming(partial)
      )
      setMessages((m) => [...m, { role: "assistant", content: res.assistant }])
      if (res.solutionReady) setSolutionReady(true)
      if (isFirst) refreshList()
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
    } finally {
      setLoading(false)
      setStreaming("")
    }
  }

  async function generate(key: ArtifactKey) {
    setArtifacts((s) => ({ ...s, [key]: { loading: true, partial: "" } }))
    try {
      const result = await api.generate({ conversationId: convId, artifact: key, messages, user }, (partial) =>
        setArtifacts((s) => ({ ...s, [key]: { ...s[key], loading: true, partial } }))
      )
      setArtifacts((s) => ({ ...s, [key]: { result } }))
    } catch (e) {
      setArtifacts((s) => ({ ...s, [key]: { error: String(e instanceof Error ? e.message : e) } }))
    }
  }

  async function generateAll() {
    setGeneratingAll(true)
    try {
      await Promise.all(ARTIFACTS.map((a) => generate(a.key)))
    } finally {
      setGeneratingAll(false)
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    const id = deleteTarget.conversationId
    setDeleting(true)
    try {
      await api.deleteConversation(id)
      setDeleteTarget(null)
      if (id === convId) newChat()
      await refreshList()
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
    } finally {
      setDeleting(false)
    }
  }

  async function downloadAll() {
    setBundling(true)
    try {
      const { downloadUrl } = await api.bundle(convId)
      if (downloadUrl) window.open(downloadUrl, "_blank")
    } finally {
      setBundling(false)
    }
  }

  const title = conversations.find((c) => c.conversationId === convId)?.title || "New conversation"

  return (
    <>
    <AppLayout
      headerSelector="#top-nav"
      toolsHide
      disableContentPaddings
      navigationWidth={300}
      navigationOpen={navOpen}
      onNavigationChange={({ detail }) => setNavOpen(detail.open)}
      navigation={
        <ConversationList
          conversations={conversations}
          activeId={convId}
          loading={listLoading}
          onSelect={selectConversation}
          onNew={newChat}
          onDelete={setDeleteTarget}
        />
      }
      splitPanelOpen={splitOpen}
      onSplitPanelToggle={({ detail }) => setSplitOpen(detail.open)}
      splitPanelPreferences={{ position: "side" }}
      splitPanel={
        <SplitPanel header="Solution artifacts" i18nStrings={SPLIT_I18N}>
          <ArtifactsView
            state={artifacts}
            activeTab={activeTab}
            onActiveTab={setActiveTab}
            onGenerate={generate}
            onGenerateAll={generateAll}
            onDownloadAll={downloadAll}
            generatingAll={generatingAll}
            bundling={bundling}
          />
        </SplitPanel>
      }
      content={
        <>
          {error && (
            <div style={{ padding: "8px 16px" }}>
              <Alert type="error" dismissible onDismiss={() => setError(null)} header="Something went wrong">
                {error}
              </Alert>
            </div>
          )}
          <ChatArea
            title={title}
            messages={messages}
            streaming={streaming}
            loading={loading}
            solutionReady={solutionReady}
            artifactsOpen={splitOpen}
            attachments={attachments}
            onToggleArtifacts={() => setSplitOpen((o) => !o)}
            onSend={send}
          />
        </>
      }
    />
    <Modal
      visible={!!deleteTarget}
      onDismiss={() => !deleting && setDeleteTarget(null)}
      header="Delete conversation"
      footer={
        <Box float="right">
          <SpaceBetween size="xs" direction="horizontal">
            <Button variant="link" disabled={deleting} onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="primary" loading={deleting} onClick={confirmDelete}>
              Delete
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      This permanently deletes "{deleteTarget?.title}" and all of its generated
      artifacts (diagram, IaC, docs). This can't be undone.
    </Modal>
    </>
  )
}
