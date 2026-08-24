/**
 * Runtime configuration.
 *
 * The CDK stack deploys a `config.json` alongside the built SPA (via an S3
 * BucketDeployment), so the exact Cognito/API identifiers are resolved at
 * deploy time rather than baked into the bundle. During local development the
 * same file can be provided in `public/config.json`.
 */
export interface AppConfig {
  region: string
  userPoolId: string
  userPoolClientId: string
  apiUrl: string
}

let cached: AppConfig | null = null

export async function loadConfig(): Promise<AppConfig> {
  if (cached) return cached
  const res = await fetch("/config.json", { cache: "no-store" })
  if (!res.ok) {
    throw new Error(`Failed to load runtime config (/config.json): ${res.status}`)
  }
  cached = (await res.json()) as AppConfig
  return cached
}

export function getConfig(): AppConfig {
  if (!cached) throw new Error("Config not loaded yet")
  return cached
}
