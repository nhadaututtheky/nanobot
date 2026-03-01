import { WifiOff, RefreshCw } from 'lucide-react'
import { useConnectionStore } from '@/stores/useConnectionStore'
import { nanobotWS } from '@/ws/client'

export function ConnectionBanner() {
  const state = useConnectionStore((s) => s.state)

  if (state === 'connected') return null

  const isReconnecting = state === 'connecting' || state === 'challenging' || state === 'authenticating'

  return (
    <div className="flex items-center justify-center gap-2 bg-warning/10 px-4 py-1.5 text-sm text-warning">
      {isReconnecting ? (
        <>
          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          <span>Reconnecting to gateway...</span>
        </>
      ) : (
        <>
          <WifiOff className="h-3.5 w-3.5" />
          <span>Disconnected from gateway</span>
          <button
            onClick={() => nanobotWS.connect()}
            className="ml-2 underline hover:no-underline"
          >
            Retry
          </button>
        </>
      )}
    </div>
  )
}
