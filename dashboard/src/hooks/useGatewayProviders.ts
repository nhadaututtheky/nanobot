import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { gatewayApi } from '@/api/gateway'
import type { ProviderAuthState, GatewayProvider, ProviderMeta } from '@/types/gateway'

const PROVIDER_META: Record<GatewayProvider, ProviderMeta> = {
  anthropic: { label: 'Claude', prefix: 'cc/', description: 'Claude Code subscription', tier: 'subscription' },
  codex: { label: 'Codex', prefix: 'cx/', description: 'OpenAI Codex subscription', tier: 'subscription' },
  gemini: { label: 'Gemini CLI', prefix: 'gc/', description: 'Google Gemini CLI (free 180K/mo)', tier: 'subscription' },
  copilot: { label: 'GitHub Copilot', prefix: 'gh/', description: 'GitHub Copilot subscription', tier: 'subscription' },
  iflow: { label: 'iFlow', prefix: 'if/', description: '8 free models, unlimited', tier: 'free' },
  qwen: { label: 'Qwen', prefix: 'qw/', description: '3 free models, unlimited', tier: 'free' },
  kiro: { label: 'Kiro', prefix: 'kr/', description: 'Free Claude via AWS Builder ID', tier: 'free' },
}

export function useGatewayProviders() {
  const queryClient = useQueryClient()

  const { data: authFiles, isLoading, error } = useQuery({
    queryKey: ['gateway', 'auth-files'],
    queryFn: () => gatewayApi.getAuthFiles(),
    refetchInterval: 60_000,
    retry: 1,
  })

  const providers: ProviderAuthState[] = (Object.keys(PROVIDER_META) as GatewayProvider[]).map((p) => {
    const meta = PROVIDER_META[p]
    const file = authFiles?.find((f) => f.provider === p || f.name.toLowerCase().includes(p))
    return {
      provider: p,
      meta,
      connected: file?.status === 'active',
      authFile: file,
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
