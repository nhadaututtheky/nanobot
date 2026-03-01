import { useState } from 'react'
import { Wifi, WifiOff, Loader2, Settings2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { StatusDot } from '@/components/common/StatusDot'
import { useGatewayHealth } from '@/hooks/useGatewayHealth'
import { GATEWAY_MGMT_URL_KEY, GATEWAY_DEFAULT_MGMT } from '@/lib/constants'

export function HealthPanel() {
  const [endpoint, setEndpoint] = useState(
    () => localStorage.getItem(GATEWAY_MGMT_URL_KEY) ?? GATEWAY_DEFAULT_MGMT
  )
  const [saved, setSaved] = useState(true)
  const { data: health, isLoading, refetch } = useGatewayHealth()

  function handleEndpointChange(value: string) {
    setEndpoint(value)
    setSaved(false)
  }

  function handleSave() {
    localStorage.setItem(GATEWAY_MGMT_URL_KEY, endpoint)
    setSaved(true)
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
        <div className="space-y-1.5">
          <Label htmlFor="gateway-endpoint">Management API URL</Label>
          <div className="flex gap-2">
            <Input
              id="gateway-endpoint"
              value={endpoint}
              onChange={(e) => handleEndpointChange(e.target.value)}
              placeholder="http://localhost:8317/v0/management"
              className="font-mono text-sm"
            />
            {!saved && (
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
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Wifi className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>

        {health && (
          <div className="flex items-center gap-2">
            {health.reachable ? (
              <>
                <Wifi className="h-4 w-4 text-success" />
                <Badge variant="outline" className="border-success/40 text-success text-xs">
                  Reachable
                </Badge>
                {health.latencyMs !== null && (
                  <span className="font-mono text-xs text-muted-foreground">{health.latencyMs}ms</span>
                )}
              </>
            ) : (
              <>
                <WifiOff className="h-4 w-4 text-destructive" />
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
      </CardContent>
    </Card>
  )
}
