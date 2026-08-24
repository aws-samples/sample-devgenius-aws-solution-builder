import Tabs from "@cloudscape-design/components/tabs"
import Button from "@cloudscape-design/components/button"
import SpaceBetween from "@cloudscape-design/components/space-between"
import Box from "@cloudscape-design/components/box"
import StatusIndicator from "@cloudscape-design/components/status-indicator"
import ExpandableSection from "@cloudscape-design/components/expandable-section"
import Link from "@cloudscape-design/components/link"
import Alert from "@cloudscape-design/components/alert"
import type { ArtifactKey, GenerateResponse } from "../types"
import Markdown from "./Markdown"
import DiagramViewer from "./DiagramViewer"
import { downloadText } from "../download"
import { drawioEditUrl } from "../drawio"

export interface ArtifactState {
  loading?: boolean
  result?: GenerateResponse
  error?: string
  partial?: string
}

interface ArtifactDef {
  key: ArtifactKey
  label: string
  blurb: string
  filename: string
  mime: string
}

const ARTIFACTS: ArtifactDef[] = [
  { key: "cost", label: "Cost", blurb: "Estimated monthly cost with current AWS pricing.", filename: "cost-estimate.md", mime: "text/markdown" },
  { key: "architecture", label: "Architecture", blurb: "A draw.io architecture and data-flow diagram.", filename: "architecture.drawio", mime: "application/xml" },
  { key: "cdk", label: "CDK", blurb: "TypeScript AWS CDK v2 stack.", filename: "cdk-stack.ts", mime: "text/plain" },
  { key: "cfn", label: "CloudFormation", blurb: "A YAML CloudFormation template, deployable in one click.", filename: "template.yaml", mime: "text/yaml" },
  { key: "terraform", label: "Terraform", blurb: "Terraform (HCL) using the AWS provider.", filename: "main.tf", mime: "text/plain" },
  { key: "documentation", label: "Documentation", blurb: "Comprehensive technical documentation.", filename: "documentation.md", mime: "text/markdown" },
]

interface ArtifactsViewProps {
  state: Partial<Record<ArtifactKey, ArtifactState>>
  activeTab: ArtifactKey
  onActiveTab: (key: ArtifactKey) => void
  onGenerate: (key: ArtifactKey) => void
  onGenerateAll: () => void
  onDownloadAll: () => void
  generatingAll: boolean
  bundling: boolean
}

export default function ArtifactsView({
  state,
  activeTab,
  onActiveTab,
  onGenerate,
  onGenerateAll,
  onDownloadAll,
  generatingAll,
  bundling,
}: ArtifactsViewProps) {
  return (
    <SpaceBetween size="m">
      <SpaceBetween size="xs" direction="horizontal">
        <Button variant="primary" iconName="gen-ai" loading={generatingAll} onClick={onGenerateAll}>
          Generate all
        </Button>
        <Button iconName="download" loading={bundling} onClick={onDownloadAll}>
          Download all
        </Button>
      </SpaceBetween>

      <Tabs
        activeTabId={activeTab}
        onChange={({ detail }) => onActiveTab(detail.activeTabId as ArtifactKey)}
        tabs={ARTIFACTS.map((a) => ({
          id: a.key,
          label: a.label,
          content: <ArtifactTab def={a} state={state[a.key]} onGenerate={() => onGenerate(a.key)} />,
        }))}
      />
    </SpaceBetween>
  )
}

function ArtifactTab({ def, state, onGenerate }: { def: ArtifactDef; state?: ArtifactState; onGenerate: () => void }) {
  const result = state?.result
  return (
    <Box padding={{ top: "m" }}>
      <SpaceBetween size="m">
        <Box color="text-body-secondary">{def.blurb}</Box>

        <SpaceBetween size="xs" direction="horizontal">
          <Button variant={result ? "normal" : "primary"} loading={state?.loading} onClick={onGenerate} iconName="gen-ai">
            {result ? "Regenerate" : "Generate"}
          </Button>
          {result && (
            <Button
              iconName="download"
              onClick={() =>
                downloadText(def.filename, def.key === "architecture" ? result.diagramXml ?? result.content : result.content, def.mime)
              }
            >
              Download
            </Button>
          )}
          {def.key === "architecture" && result?.diagramXml && (
            <Button iconName="edit" href={drawioEditUrl(result.diagramXml)} target="_blank">
              Edit in draw.io
            </Button>
          )}
        </SpaceBetween>

        {state?.loading && (
          <SpaceBetween size="xs">
            <StatusIndicator type="loading">Generating with live web search...</StatusIndicator>
            {def.key !== "architecture" && state.partial && (
              <Box className="dg-artifact">
                <Markdown>{state.partial}</Markdown>
              </Box>
            )}
          </SpaceBetween>
        )}
        {state?.error && (
          <Alert type="error" header="Generation failed">
            {state.error}
          </Alert>
        )}

        {result && (
          <SpaceBetween size="m">
            {def.key === "architecture" ? (
              result.diagramXml ? (
                <DiagramViewer xml={result.diagramXml} />
              ) : (
                <Alert type="warning">The diagram could not be rendered - click Regenerate.</Alert>
              )
            ) : (
              <Box className="dg-artifact">
                <Markdown>{result.content}</Markdown>
              </Box>
            )}

            {result.citations?.length > 0 && (
              <ExpandableSection headerText={`Sources (${result.citations.length})`} variant="footer">
                <SpaceBetween size="xs">
                  {result.citations.map((c, i) => (
                    <Link key={i} href={c.url} external>
                      {c.title || c.url}
                    </Link>
                  ))}
                </SpaceBetween>
              </ExpandableSection>
            )}
          </SpaceBetween>
        )}
      </SpaceBetween>
    </Box>
  )
}

export { ARTIFACTS }
