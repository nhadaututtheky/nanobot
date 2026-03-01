import { PageHeader } from '@/components/common/PageHeader'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { HealthPanel } from './HealthPanel'
import { ProviderGrid } from './ProviderGrid'
import { UsagePanel } from './UsagePanel'

export function GatewayPage() {
  return (
    <ErrorBoundary>
      <PageHeader
        title="AI Gateway"
        description="Manage LLM provider connections and OAuth authentication"
      />
      <div className="space-y-6">
        <HealthPanel />
        <div>
          <h3 className="mb-3 text-sm font-medium text-muted-foreground">Providers</h3>
          <ProviderGrid />
        </div>
        <UsagePanel />
      </div>
    </ErrorBoundary>
  )
}
