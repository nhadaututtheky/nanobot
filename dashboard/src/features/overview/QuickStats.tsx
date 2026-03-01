import { Users, MessageSquare, Clock, Coins } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { rpc } from '@/ws/rpc'
import { StatusCard } from '@/components/StatusCard'
import { formatCompact } from '@/lib/utils'

export function QuickStats() {
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['status'],
    queryFn: () => rpc.system.status(),
    refetchInterval: 30_000,
  })

  const { data: presence, isLoading: presenceLoading } = useQuery({
    queryKey: ['system-presence'],
    queryFn: () => rpc.system.systemPresence(),
    refetchInterval: 30_000,
  })

  const { data: cost, isLoading: costLoading } = useQuery({
    queryKey: ['usage-cost'],
    queryFn: () => rpc.system.usageCost(),
    refetchInterval: 60_000,
  })

  const statusData = status as Record<string, unknown> | undefined
  const presenceData = presence as Array<unknown> | undefined
  const costData = cost as Record<string, unknown> | undefined

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatusCard
        icon={<MessageSquare className="h-5 w-5" />}
        label="Sessions"
        value={String(statusData?.['activeSessions'] ?? '—')}
        loading={statusLoading}
      />
      <StatusCard
        icon={<Users className="h-5 w-5" />}
        label="Clients"
        value={String(presenceData?.length ?? '—')}
        loading={presenceLoading}
      />
      <StatusCard
        icon={<Clock className="h-5 w-5" />}
        label="Cron Jobs"
        value={String(statusData?.['cronJobs'] ?? '—')}
        loading={statusLoading}
      />
      <StatusCard
        icon={<Coins className="h-5 w-5" />}
        label="Tokens Today"
        value={costData?.['totalTokens'] ? formatCompact(costData['totalTokens'] as number) : '—'}
        loading={costLoading}
      />
    </div>
  )
}
