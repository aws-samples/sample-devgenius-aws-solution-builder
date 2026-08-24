import { useMemo } from "react"

/**
 * Renders a draw.io / diagrams.net XML document using the official static
 * viewer, sandboxed inside an iframe (via srcdoc) so the third-party viewer
 * script cannot touch the rest of the app.
 */
export default function DiagramViewer({ xml }: { xml: string }) {
  const srcDoc = useMemo(() => buildSrcDoc(xml), [xml])
  return (
    <iframe
      title="Architecture diagram"
      srcDoc={srcDoc}
      sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
      style={{ width: "100%", height: 480, border: "1px solid var(--color-border-divider-default, #d5dbdb)", borderRadius: 8 }}
    />
  )
}

function buildSrcDoc(xml: string): string {
  const config = {
    highlight: "#0073bb",
    nav: true,
    resize: true,
    toolbar: "zoom layers lightbox edit",
    edit: "_blank", // shows an edit button that opens the diagram in diagrams.net
    xml,
  }
  const attr = JSON.stringify(config)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")

  return `<!doctype html>
<html>
  <head><meta charset="utf-8" /><style>html,body{margin:0;height:100%;background:#fff}</style></head>
  <body>
    <div class="mxgraph" style="max-width:100%" data-mxgraph="${attr}"></div>
    <script src="https://viewer.diagrams.net/js/viewer-static.min.js"></script>
  </body>
</html>`
}
