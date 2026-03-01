import { useGatewayProviders } from '@/hooks/useGatewayProviders'
import { useGatewayAuth } from '@/hooks/useGatewayAuth'
import { useGatewayHealth } from '@/hooks/useGatewayHealth'
import { ProviderCard } from './ProviderCard'
import { OAuthProgressDialog } from './OAuthProgressDialog'
import { Skeleton } from '@/components/ui/skeleton'

export function ProviderGrid() {
  const { providers, isLoading, disconnect, isDisconnecting } = useGatewayProviders()
  const { flowState, startOAuth, cancelOAuth, reopenAuthUrl } = useGatewayAuth()
  const { data: health } = useGatewayHealth()
  const gatewayReachable = health?.reachable ?? false

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-32 rounded-xl" />
        ))}
      </div>
    )
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {providers.map((p) => (
          <ProviderCard
            key={p.provider}
            state={p}
            oauthFlow={flowState}
            onConnect={startOAuth}
            onDisconnect={disconnect}
            isDisconnecting={isDisconnecting}
            gatewayReachable={gatewayReachable}
          />
        ))}
      </div>
      <OAuthProgressDialog
        flowState={flowState}
        onCancel={cancelOAuth}
        onReopenUrl={reopenAuthUrl}
      />
    </>
  )
}
