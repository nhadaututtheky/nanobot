import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { gatewayApi } from '@/api/gateway'
import type { AuthFile, ProviderAuthState, GatewayProvider, ProviderMeta } from '@/types/gateway'

const PROVIDER_META: Record<GatewayProvider, ProviderMeta> = {
  anthropic: { label: 'Claude', prefix: 'cc/', description: 'Claude Code subscription', tier: 'subscription' },
  codex: { label: 'Codex', prefix: 'cx/', description: 'OpenAI Codex subscription', tier: 'subscription' },
  gemini: { label: 'Gemini CLI', prefix: 'gc/', description: 'Google Gemini CLI (free 180K/mo)', tier: 'subscription' },
  copilot: { label: 'GitHub Copilot', prefix: 'gh/', description: 'GitHub Copilot subscription', tier: 'subscription' },
  iflow: { label: 'iFlow', prefix: 'if/', description: '8 free models, unlimited', tier: 'free' },
  qwen: { label: 'Qwen', prefix: 'qw/', description: '3 free models, unlimited', tier: 'free' },
  kiro: { label: 'Kiro', prefix: 'kr/', description: 'Free Claude via AWS Builder ID', tier: 'free' },
}

// Map server provider names → our UI provider keys
const SERVER_PROVIDER_MAP: Record<string, GatewayProvider> = {
  'claude': 'anthropic',
  'anthropic': 'anthropic',
  'codex': 'codex',
  'gemini-cli': 'gemini',
  'gemini': 'gemini',
  'antigravity': 'gemini', // Antigravity is Gemini-based
  'iflow': 'iflow',
  'qwen': 'qwen',
  'kiro': 'kiro',
  'copilot': 'copilot',
  'github-copilot': 'copilot',
}

function matchProvider(file: AuthFile): GatewayProvider | null {
  // Direct map from server provider/type field
  const mapped = SERVER_PROVIDER_MAP[file.provider] ?? SERVER_PROVIDER_MAP[file.type]
  if (mapped) return mapped
  // Fallback: check name substring
  const nameLower = file.name.toLowerCase()
  for (const [key, provider] of Object.entries(SERVER_PROVIDER_MAP)) {
    if (nameLower.includes(key)) return provider
  }
  return null
}

export function useGatewayProviders() {
  const queryClient = useQueryClient()

  const { data: authFiles, isLoading, error } = useQuery({
    queryKey: ['gateway', 'auth-files'],
    queryFn: () => gatewayApi.getAuthFiles(),
    refetchInterval: 60_000,
    retry: 1,
  })

  // Group auth files by provider
  const filesByProvider = new Map<GatewayProvider, AuthFile[]>()
  for (const file of authFiles ?? []) {
    const provider = matchProvider(file)
    if (provider) {
      const list = filesByProvider.get(provider) ?? []
      list.push(file)
      filesByProvider.set(provider, list)
    }
  }

  const providers: ProviderAuthState[] = (Object.keys(PROVIDER_META) as GatewayProvider[]).map((p) => {
    const meta = PROVIDER_META[p]
    const files = filesByProvider.get(p) ?? []
    const activeFiles = files.filter((f) => f.status === 'active' && !f.disabled)
    const primaryFile = activeFiles[0] ?? files[0]
    return {
      provider: p,
      meta,
      connected: activeFiles.length > 0,
      authFile: primaryFile,
      connectedCount: activeFiles.length,
    }
  })

  const disconnectMutation = useMutation({
    mutationFn: (name: string) => gatewayApi.deleteAuthFile(name),
    onSuccess: () => {
      toast.success('Provider disconnected')
      void queryClient.invalidateQueries({ queryKey: ['gateway', 'auth-files'] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Failed to disconnect'
      toast.error('Disconnect failed', { description: msg })
    },
  })

  return {
    providers,
    isLoading,
    error,
    disconnect: disconnectMutation.mutate,
    isDisconnecting: disconnectMutation.isPending,
  }
}

export { PROVIDER_META }
