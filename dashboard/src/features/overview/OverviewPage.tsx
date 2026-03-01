import { PageHeader } from '@/components/common/PageHeader'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { QuickStats } from './QuickStats'
import { SystemHealthCard } from './SystemHealthCard'
import { ChannelsGrid } from './ChannelsGrid'
import { ActivityFeed } from './ActivityFeed'

export function OverviewPage() {
  return (
    <ErrorBoundary>
      <PageHeader
        title="Overview"
        description="System status and real-time monitoring"
      />
      <div className="space-y-6">
        <QuickStats />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
          <div className="space-y-6 lg:col-span-3">
            <SystemHealthCard />
            <ChannelsGrid />
          </div>
          <div className="lg:col-span-2">
            <ActivityFeed />
          </div>
        </div>
      </div>
    </ErrorBoundary>
  )
}
