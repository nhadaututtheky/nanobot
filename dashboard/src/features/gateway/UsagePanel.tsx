import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Activity, CheckCircle2, XCircle, Coins } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { gatewayApi } from '@/api/gateway'
import { useGatewayHealth } from '@/hooks/useGatewayHealth'
import { formatCompact } from '@/lib/utils'

interface GatewayUsage {
  total_requests: number
  success_count: number
  failure_count: number
  total_tokens: number
  apis?: Record<string, { requests: number; tokens: number }>
  requests_by_day?: Record<string, number>
  tokens_by_day?: Record<string, number>
}

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
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    )
  }

  const u = usage as GatewayUsage | undefined
  const totalReq = u?.total_requests ?? 0
  const successCount = u?.success_count ?? 0
  const failureCount = u?.failure_count ?? 0
  const totalTokens = u?.total_tokens ?? 0
  const apis = u?.apis ?? {}
  const apiEntries = Object.entries(apis).filter(([, v]) => v && v.requests > 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <BarChart3 className="h-4 w-4" />
          Usage Statistics
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Summary stats */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatItem
            icon={<Activity className="h-4 w-4 text-primary" />}
            label="Total Requests"
            value={formatCompact(totalReq)}
          />
          <StatItem
            icon={<CheckCircle2 className="h-4 w-4 text-success" />}
            label="Successful"
            value={formatCompact(successCount)}
          />
          <StatItem
            icon={<XCircle className="h-4 w-4 text-destructive" />}
            label="Failed"
            value={formatCompact(failureCount)}
          />
          <StatItem
            icon={<Coins className="h-4 w-4 text-warning" />}
            label="Total Tokens"
            value={formatCompact(totalTokens)}
          />
        </div>

        {/* Per-API breakdown */}
        {apiEntries.length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Per Provider
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="px-3 py-1.5 text-left font-medium">Provider</th>
                    <th className="px-3 py-1.5 text-right font-medium">Requests</th>
                    <th className="px-3 py-1.5 text-right font-medium">Tokens</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {apiEntries.map(([name, data]) => (
                    <tr key={name} className="hover:bg-muted/20 transition-colors">
                      <td className="px-3 py-1.5 font-mono text-xs">{name}</td>
                      <td className="px-3 py-1.5 text-right font-mono text-xs">{formatCompact(data.requests)}</td>
                      <td className="px-3 py-1.5 text-right font-mono text-xs">{formatCompact(data.tokens)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {totalReq === 0 && (
          <p className="text-sm text-muted-foreground text-center py-2">
            No requests yet. Usage data will appear after routing traffic through the gateway.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function StatItem({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg bg-muted/30 px-3 py-2.5">
      {icon}
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="font-mono text-sm font-bold">{value}</p>
      </div>
    </div>
  )
}
