import { useState } from 'react'
import { Wifi, WifiOff, Loader2, Router } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

interface NineRouterSectionProps {
  endpoint: string
  onEndpointChange: (value: string) => void
}

type HealthStatus = 'idle' | 'checking' | 'ok' | 'error'

export function NineRouterSection({ endpoint, onEndpointChange }: NineRouterSectionProps) {
  const [status, setStatus] = useState<HealthStatus>('idle')
  const [latencyMs, setLatencyMs] = useState<number | null>(null)

  async function handleHealthCheck() {
    setStatus('checking')
    setLatencyMs(null)
    const start = performance.now()
    try {
      const res = await fetch(endpoint, { signal: AbortSignal.timeout(5000) })
      const elapsed = Math.round(performance.now() - start)
      setLatencyMs(elapsed)
      setStatus(res.ok ? 'ok' : 'error')
    } catch {
      setStatus('error')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Router className="h-4 w-4" />
          9Router Integration
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          9Router provides an OpenAI-compatible proxy endpoint that routes requests
          through configured LLM providers. NanoBot can use it as a drop-in provider.
        </p>
        <div className="space-y-1.5">
          <Label htmlFor="ninerouter-endpoint">Endpoint URL</Label>
          <div className="flex gap-2">
            <Input
              id="ninerouter-endpoint"
              value={endpoint}
              onChange={(e) => onEndpointChange(e.target.value)}
              placeholder="http://localhost:20128/v1"
              className="font-mono text-sm"
            />
            <Button
              variant="outline"
              size="sm"
              onClick={handleHealthCheck}
              disabled={status === 'checking' || !endpoint}
              aria-label="Check 9router health"
            >
              {status === 'checking' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Wifi className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
        {status !== 'idle' && status !== 'checking' && (
          <div className="flex items-center gap-2">
            {status === 'ok' ? (
              <>
                <Wifi className="h-4 w-4 text-success" />
                <Badge variant="outline" className="border-success text-success text-xs">
                  Reachable
                </Badge>
                {latencyMs !== null && (
                  <span className="font-mono text-xs text-muted-foreground">{latencyMs}ms</span>
                )}
              </>
            ) : (
              <>
                <WifiOff className="h-4 w-4 text-destructive" />
                <Badge variant="outline" className="border-destructive text-destructive text-xs">
                  Unreachable
                </Badge>
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
