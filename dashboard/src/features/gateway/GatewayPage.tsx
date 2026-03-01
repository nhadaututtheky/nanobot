import { PageHeader } from '@/components/common/PageHeader'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { ActiveProviderPanel } from './ActiveProviderPanel'
import { HealthPanel } from './HealthPanel'
import { ProviderGrid } from './ProviderGrid'
import { ApiKeyGrid } from './ApiKeyGrid'
import { UsagePanel } from './UsagePanel'

export function GatewayPage() {
  return (
    <ErrorBoundary>
      <PageHeader
        title="AI Gateway"
        description="Manage LLM provider connections, API keys, and model routing"
      />
      <div className="space-y-8">
        <ActiveProviderPanel />
        <HealthPanel />
        <div>
          <h3 className="mb-4 text-base font-semibold">OAuth Providers</h3>
          <ProviderGrid />
        </div>
        <div>
          <h3 className="mb-4 text-base font-semibold">API Keys</h3>
          <ApiKeyGrid />
        </div>
        <UsagePanel />
      </div>
    </ErrorBoundary>
  )
}
