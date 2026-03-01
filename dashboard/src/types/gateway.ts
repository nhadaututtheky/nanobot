export interface AuthFile {
  name: string
  id: string
  provider: string
  type: string
  status: 'active' | 'expired' | 'disabled' | 'unknown'
  email?: string
  account?: string
  label?: string
  source?: string
  disabled?: boolean
  unavailable?: boolean
  runtime_only?: boolean
  metadata?: Record<string, unknown>
}

export type GatewayProvider =
  | 'anthropic'
  | 'codex'
  | 'gemini'
  | 'iflow'
  | 'qwen'
  | 'kiro'
  | 'copilot'

export interface ProviderMeta {
  label: string
  prefix: string
  description: string
  tier: 'subscription' | 'cheap' | 'free'
}

export interface ProviderAuthState {
  provider: GatewayProvider
  meta: ProviderMeta
  connected: boolean
  authFile?: AuthFile
  connectedCount?: number
}

export type OAuthFlowState =
  | { phase: 'idle' }
  | { phase: 'opening'; provider: GatewayProvider }
  | { phase: 'polling'; provider: GatewayProvider; state: string; attempts: number; authUrl: string }
  | { phase: 'success'; provider: GatewayProvider }
  | { phase: 'error'; provider: GatewayProvider; message: string }

export interface UsageData {
  [key: string]: unknown
}

export interface GatewayHealthResult {
  reachable: boolean
  latencyMs: number | null
  error?: string
}
