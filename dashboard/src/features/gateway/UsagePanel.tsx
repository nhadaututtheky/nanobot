import { useQuery } from '@tanstack/react-query'
import { BarChart3 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { gatewayApi } from '@/api/gateway'
import { useGatewayHealth } from '@/hooks/useGatewayHealth'

export function UsagePanel() {
  const { data: health } = useGatewayHealth()
  const gatewayReachable = health?.reachable ?? false

  const { data: usage, isLoading } = useQuery({
    queryKey: ['gateway', 'usage'],
    queryFn: () => gatewayApi.getUsage(),
    refetchInterval: 60_000,
    retry: 1,
    enabled: gatewayReachable,
  })

  if (!gatewayReachable) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <BarChart3 className="h-4 w-4" />
            Usage Statistics
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Connect to the AI Gateway to view usage statistics.
          </p>
        </CardContent>
      </Card>
    )
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <BarChart3 className="h-4 w-4" />
            Usage Statistics
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-4 w-36" />
          <Skeleton className="h-4 w-56" />
        </CardContent>
      </Card>
    )
  }

  // Usage data format varies by gateway implementation — render as key-value pairs
  const entries = usage
    ? Object.entries(usage).filter(([, v]) => v !== null && v !== undefined)
    : []

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <BarChart3 className="h-4 w-4" />
          Usage Statistics
        </CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No usage data available yet.</p>
        ) : (
          <div className="space-y-2">
            {entries.map(([key, value]) => (
              <div key={key} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground capitalize">
                  {key.replace(/[_-]/g, ' ')}
                </span>
                <span className="font-mono font-medium">
                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
