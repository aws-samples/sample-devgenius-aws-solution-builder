import Box from "@cloudscape-design/components/box"
import Alert from "@cloudscape-design/components/alert"
import ContentLayout from "@cloudscape-design/components/content-layout"
import Header from "@cloudscape-design/components/header"

/** Fallback screen shown when runtime configuration cannot be loaded. */
export default function Bootstrap({ error }: { error: string }) {
  return (
    <ContentLayout header={<Header variant="h1">DevGenius</Header>}>
      <Box margin={{ top: "l" }}>
        <Alert type="error" header="Unable to start the application">
          The runtime configuration (<code>/config.json</code>) could not be loaded.
          If you are running locally, add a <code>public/config.json</code> with your
          Cognito and API details.
          <Box variant="code" margin={{ top: "s" }}>
            {error}
          </Box>
        </Alert>
      </Box>
    </ContentLayout>
  )
}
