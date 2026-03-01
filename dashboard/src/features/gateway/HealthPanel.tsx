import { useState } from 'react'
import { Wifi, Loader2, Settings2, Play, Square, Eye, EyeOff } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { StatusDot } from '@/components/common/StatusDot'
import { useGatewayHealth } from '@/hooks/useGatewayHealth'
import {
  GATEWAY_MGMT_URL_KEY,
  GATEWAY_MGMT_KEY_KEY,
  GATEWAY_DEFAULT_MGMT,
} from '@/lib/constants'
import { rpc } from '@/ws/rpc'

interface AiGatewayStatus {
  running: boolean
  pid: number | null
  binaryFound: boolean
  binaryPath: string | null
  managementUrl: string
  proxyUrl: string
  enabled: boolean
}

export function HealthPanel() {
  const queryClient = useQueryClient()
  const [endpoint, setEndpoint] = useState(
    () => localStorage.getItem(GATEWAY_MGMT_URL_KEY) ?? GATEWAY_DEFAULT_MGMT
  )
  const [mgmtKey, setMgmtKey] = useState(
    () => localStorage.getItem(GATEWAY_MGMT_KEY_KEY) ?? ''
  )
  const [showKey, setShowKey] = useState(false)
  const [dirty, setDirty] = useState(false)
  const { data: health, isLoading, refetch } = useGatewayHealth()

  // AI Gateway service status (via NanoBot WS RPC)
  const { data: serviceStatus } = useQuery({
    queryKey: ['ai-gateway', 'status'],
    queryFn: () => rpc.aiGateway.status(),
    refetchInterval: 10_000,
    retry: 1,
  })

  const svc = serviceStatus as AiGatewayStatus | undefined

  const startMutation = useMutation({
    mutationFn: () => rpc.aiGateway.start(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-gateway'] })
      setTimeout(() => void refetch(), 2000)
    },
  })

  const stopMutation = useMutation({
    mutationFn: () => rpc.aiGateway.stop(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-gateway'] })
      void refetch()
    },
  })

  const isMutating = startMutation.isPending || stopMutation.isPending

  function handleSave() {
    localStorage.setItem(GATEWAY_MGMT_URL_KEY, endpoint)
    localStorage.setItem(GATEWAY_MGMT_KEY_KEY, mgmtKey)
    setDirty(false)
    void refetch()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Settings2 className="h-4 w-4" />
          Gateway Connection
          {health && !isLoading && (
            <StatusDot status={health.reachable ? 'online' : 'offline'} className="ml-auto" />
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Endpoint URL + Management Key */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="gateway-endpoint">Management API URL</Label>
            <Input
              id="gateway-endpoint"
              value={endpoint}
              onChange={(e) => { setEndpoint(e.target.value); setDirty(true) }}
              placeholder="http://localhost:8317/v0/management"
              className="font-mono text-sm"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gateway-key">Management Key</Label>
            <div className="flex gap-1.5">
              <div className="relative flex-1">
                <Input
                  id="gateway-key"
                  type={showKey ? 'text' : 'password'}
                  value={mgmtKey}
                  onChange={(e) => { setMgmtKey(e.target.value); setDirty(true) }}
                  placeholder="Secret key (if set)"
                  className="pr-9 font-mono text-sm"
                />
                <button
                  type="button"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
                  onClick={() => setShowKey((v) => !v)}
                  aria-label={showKey ? 'Hide key' : 'Show key'}
                >
                  {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Save + Test row */}
        <div className="flex items-center gap-2">
          {dirty && (
            <Button variant="outline" size="sm" onClick={handleSave}>
              Save
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refetch()}
            disabled={isLoading}
            aria-label="Test connection"
          >
            {isLoading ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Wifi className="mr-1 h-3.5 w-3.5" />
            )}
            Test
          </Button>

          {/* Health result */}
          {health && (
            <div className="flex items-center gap-2">
              {health.reachable ? (
                <>
                  <Badge variant="outline" className="border-success/40 text-success text-xs">
                    Reachable
                  </Badge>
                  {health.latencyMs !== null && (
                    <span className="font-mono text-xs text-muted-foreground">{health.latencyMs}ms</span>
                  )}
                </>
              ) : (
                <>
                  <Badge variant="outline" className="border-destructive/40 text-destructive text-xs">
                    Unreachable
                  </Badge>
                  {health.error && (
                    <span className="text-xs text-muted-foreground truncate max-w-[200px]">{health.error}</span>
                  )}
                </>
              )}
            </div>
          )}

          {/* Service start/stop — pushed to right */}
          <div className="flex items-center gap-2 ml-auto">
            {svc?.running || health?.reachable ? (
              <>
                {svc?.running && svc.pid && (
                  <Badge variant="outline" className="border-success/40 text-success text-xs">
                    PID {svc.pid}
                  </Badge>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs text-destructive hover:text-destructive"
                  onClick={() => stopMutation.mutate()}
                  disabled={isMutating}
                  aria-label="Stop AI Gateway"
                >
                  {stopMutation.isPending ? (
                    <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  ) : (
                    <Square className="mr-1 h-3 w-3" />
                  )}
                  Stop Gateway
                </Button>
              </>
            ) : svc?.binaryFound ? (
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={() => startMutation.mutate()}
                disabled={isMutating}
                aria-label="Start AI Gateway"
              >
                {startMutation.isPending ? (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                ) : (
                  <Play className="mr-1 h-3 w-3" />
                )}
                Start Gateway
              </Button>
            ) : svc ? (
              <span className="text-xs text-muted-foreground">
                Binary not found
              </span>
            ) : null}
          </div>
        </div>

        {/* Mutation error messages */}
        {startMutation.isError && (
          <p className="text-xs text-destructive">
            Start failed: {startMutation.error instanceof Error ? startMutation.error.message : 'Unknown error'}
          </p>
        )}
        {stopMutation.isError && (
          <p className="text-xs text-destructive">
            Stop failed: {stopMutation.error instanceof Error ? stopMutation.error.message : 'Unknown error'}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
