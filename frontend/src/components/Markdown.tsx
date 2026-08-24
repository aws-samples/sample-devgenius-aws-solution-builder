import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import Link from "@cloudscape-design/components/link"
import Box from "@cloudscape-design/components/box"

/**
 * Renders model markdown with Cloudscape-styled links and readable tables.
 * Kept intentionally simple - the content is trusted model output shown to the
 * signed-in user, and code blocks are displayed as preformatted text.
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <Box variant="div" className="dg-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <Link href={href} external>
              {children}
            </Link>
          ),
          table: ({ children }) => (
            <div className="dg-table-wrap">
              <table className="dg-table">{children}</table>
            </div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </Box>
  )
}
