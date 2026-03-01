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
  const presenceRaw = presence as { clients?: unknown[] } | unknown[] | undefined
  const presenceList = Array.isArray(presenceRaw) ? presenceRaw : (presenceRaw?.clients ?? [])
  const costData = cost as Record<string, unknown> | undefined

  // Server status: { agent, channels, cron, heartbeat, gateway }
  const cronObj = statusData?.['cron'] as Record<string, unknown> | undefined
  const channelsObj = statusData?.['channels'] as Record<string, boolean> | undefined
  const activeChannels = channelsObj ? Object.values(channelsObj).filter(Boolean).length : 0

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatusCard
        icon={<MessageSquare className="h-5 w-5" />}
        label="Channels"
        value={String(activeChannels || '—')}
        loading={statusLoading}
      />
      <StatusCard
        icon={<Users className="h-5 w-5" />}
        label="Clients"
        value={String(presenceList.length || '—')}
        loading={presenceLoading}
      />
      <StatusCard
        icon={<Clock className="h-5 w-5" />}
        label="Cron Jobs"
        value={String(cronObj?.['jobs'] ?? '—')}
        loading={statusLoading}
      />
      <StatusCard
        icon={<Coins className="h-5 w-5" />}
        label="Cost Today"
        value={costData?.['totalCost'] ? `$${formatCompact(costData['totalCost'] as number)}` : '—'}
        loading={costLoading}
      />
    </div>
  )
}
