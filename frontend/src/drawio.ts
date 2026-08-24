/**
 * Build a diagrams.net URL that opens the given draw.io XML in the editor
 * (new tab) so the user can edit it. The `#R` fragment carries the raw,
 * URL-encoded diagram XML, which diagrams.net loads directly for editing.
 */
export function drawioEditUrl(xml: string): string {
  return `https://app.diagrams.net/?title=architecture.drawio&splash=0#R${encodeURIComponent(xml)}`
}
