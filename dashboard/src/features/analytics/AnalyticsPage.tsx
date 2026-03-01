import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Coins, MessageSquare } from 'lucide-react'
import { rpc } from '@/ws/rpc'
import { PageHeader } from '@/components/common/PageHeader'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { StatusCard } from '@/components/StatusCard'
import { UsageTimeseries } from './UsageTimeseries'
import { CostBreakdown } from './CostBreakdown'
import { SessionUsageTable } from './SessionUsageTable'
import { formatCompact } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CostData {
  totalCost: number
  totalTokens: number
  currency: string
}

interface SessionItem {
  sessionKey: string
}

// ---------------------------------------------------------------------------
// AnalyticsPage
// ---------------------------------------------------------------------------

export function AnalyticsPage() {
  const [selectedSession, setSelectedSession] = useState<string>('')

  const { data: cost, isLoading: costLoading } = useQuery({
    queryKey: ['usage-cost'],
    queryFn: () => rpc.system.usageCost(),
    select: (d) => d as CostData,
    refetchInterval: 60_000,
  })

  const { data: sessions, isLoading: sessionsLoading } = useQuery({
    queryKey: ['sessions-list'],
    queryFn: () => rpc.sessions.list(),
    select: (d) => d as SessionItem[],
    refetchInterval: 60_000,
  })

  const sessionKeys = sessions?.map((s) => s.sessionKey) ?? []

  const handleSessionSelect = useCallback((key: string) => {
    setSelectedSession(key)
  }, [])

  function formatCost(value: number, currency = 'USD'): string {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      minimumFractionDigits: 4,
      maximumFractionDigits: 4,
    }).format(value)
  }

  return (
    <ErrorBoundary>
      <PageHeader
        title="Analytics"
        description="Usage metrics and cost tracking"
      />

      <div className="space-y-6">
        {/* Overview cards */}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          <StatusCard
            icon={<Coins className="h-5 w-5" />}
            label="Total Cost"
            value={
              cost
                ? formatCost(cost.totalCost, cost.currency)
                : '—'
            }
            loading={costLoading}
          />
          <StatusCard
            icon={<BarChart3 className="h-5 w-5" />}
            label="Total Tokens"
            value={cost?.totalTokens ? formatCompact(cost.totalTokens) : '—'}
            loading={costLoading}
          />
          <StatusCard
            icon={<MessageSquare className="h-5 w-5" />}
            label="Sessions"
            value={sessions ? String(sessions.length) : '—'}
            loading={sessionsLoading}
            className="col-span-2 lg:col-span-1"
          />
        </div>

        {/* Timeseries chart */}
        <UsageTimeseries
          sessionKeys={selectedSession ? [selectedSession, ...sessionKeys.filter((k) => k !== selectedSession)] : sessionKeys}
        />

        {/* Cost + session table */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <CostBreakdown />
          </div>
          <div className="lg:col-span-3">
            <SessionUsageTable onSessionSelect={handleSessionSelect} />
          </div>
        </div>
      </div>
    </ErrorBoundary>
  )
}
