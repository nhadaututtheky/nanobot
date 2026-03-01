import { Activity, Server, Clock } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { rpc } from '@/ws/rpc'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusDot } from '@/components/common/StatusDot'
import { formatDuration } from '@/lib/utils'

export function SystemHealthCard() {
  const { data, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: () => rpc.system.health(),
    refetchInterval: 30_000,
  })

  const health = data as Record<string, unknown> | undefined

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4" />
            System Health
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-4 w-36" />
          <Skeleton className="h-4 w-40" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-4 w-4" />
          System Health
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="flex items-center gap-2">
            <StatusDot status={health?.['ok'] ? 'online' : 'error'} />
            <span className="text-muted-foreground">Status</span>
            <span className="ml-auto font-medium">
              {health?.['ok'] ? 'Healthy' : 'Unhealthy'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Clock className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Uptime</span>
            <span className="ml-auto font-mono-bold text-xs">
              {health?.['uptimeMs'] ? formatDuration(health['uptimeMs'] as number) : '—'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Server className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Platform</span>
            <span className="ml-auto text-xs">{String(health?.['platform'] ?? '—')}</span>
          </div>
          <div className="flex items-center gap-2">
            <Server className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Python</span>
            <span className="ml-auto font-mono text-xs">{String(health?.['pythonVersion'] ?? '—')}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
