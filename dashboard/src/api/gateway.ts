import {
  GATEWAY_MGMT_URL_KEY,
  GATEWAY_MGMT_KEY_KEY,
  GATEWAY_DEFAULT_MGMT,
  GATEWAY_TIMEOUT_MS,
} from '@/lib/constants'
import type { AuthFile, UsageData, GatewayHealthResult } from '@/types/gateway'

function getBase(): string {
  return localStorage.getItem(GATEWAY_MGMT_URL_KEY) ?? GATEWAY_DEFAULT_MGMT
}

function getHeaders(): HeadersInit {
  const key = localStorage.getItem(GATEWAY_MGMT_KEY_KEY)
  return key ? { 'X-Management-Key': key } : {}
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${getBase()}${path}`, {
    headers: getHeaders(),
    signal: AbortSignal.timeout(GATEWAY_TIMEOUT_MS),
  })
  if (!res.ok) throw new Error(`Gateway ${path}: ${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${getBase()}${path}`, {
    method: 'DELETE',
    headers: getHeaders(),
    signal: AbortSignal.timeout(GATEWAY_TIMEOUT_MS),
  })
  if (!res.ok) throw new Error(`Gateway DELETE ${path}: ${res.status} ${res.statusText}`)
}

export const gatewayApi = {
  // Health check — ping /auth-files to confirm management API is reachable + key valid
  async health(): Promise<GatewayHealthResult> {
    const start = performance.now()
    try {
      const res = await fetch(`${getBase()}/auth-files`, {
        headers: getHeaders(),
        signal: AbortSignal.timeout(5000),
      })
      const latencyMs = Math.round(performance.now() - start)
      if (res.status === 401) {
        return { reachable: false, latencyMs, error: 'Invalid management key' }
      }
      return { reachable: res.ok, latencyMs }
    } catch (err) {
      return {
        reachable: false,
        latencyMs: null,
        error: err instanceof Error ? err.message : 'Connection failed',
      }
    }
  },

  // OAuth flows — each returns { url, state }
  getAnthropicAuthUrl: () => get<{ url: string; state: string }>('/anthropic-auth-url'),
  getCodexAuthUrl: () => get<{ url: string; state: string }>('/codex-auth-url'),
  getGeminiAuthUrl: (projectId?: string) => {
    const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
    return get<{ url: string; state: string }>(`/gemini-cli-auth-url${qs}`)
  },
  getIFlowAuthUrl: () => get<{ url: string; state: string }>('/iflow-auth-url'),
  getQwenAuthUrl: () => get<{ url: string; state: string }>('/qwen-auth-url'),

  // Poll OAuth status
  getAuthStatus: (state: string) =>
    get<{ completed: boolean; success?: boolean; error?: string }>(
      `/get-auth-status?state=${encodeURIComponent(state)}`
    ),

  // Auth file management
  getAuthFiles: async () => {
    const raw = await get<{ files?: AuthFile[] } | AuthFile[]>('/auth-files')
    return Array.isArray(raw) ? raw : (raw.files ?? [])
  },
  deleteAuthFile: (name: string) => del(`/auth-files?name=${encodeURIComponent(name)}`),

  // Usage stats
  getUsage: () => get<UsageData>('/usage'),

  // Config
  getConfig: () => get<Record<string, unknown>>('/config'),
}
