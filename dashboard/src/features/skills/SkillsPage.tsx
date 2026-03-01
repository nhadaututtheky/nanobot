import { Puzzle, Server } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { InstalledSkillsPanel } from './InstalledSkillsPanel'
import { MarketplaceSearch } from './MarketplaceSearch'
import { MCPServersPanel } from './MCPServersPanel'

export function SkillsPage() {
  return (
    <ErrorBoundary>
      <PageHeader
        title="Skills & Plugins"
        description="Browse, install, and manage skills from ClawHub marketplace. Configure MCP servers."
      />

      <div className="space-y-8">
        {/* Installed Skills */}
        <section>
          <h3 className="mb-4 flex items-center gap-2 text-base font-semibold">
            <Puzzle className="h-4 w-4" />
            Installed Skills
          </h3>
          <InstalledSkillsPanel />
        </section>

        {/* Marketplace Search */}
        <section>
          <h3 className="mb-4 text-base font-semibold">
            ClawHub Marketplace
          </h3>
          <MarketplaceSearch />
        </section>

        {/* MCP Servers */}
        <section>
          <h3 className="mb-4 flex items-center gap-2 text-base font-semibold">
            <Server className="h-4 w-4" />
            MCP Servers
          </h3>
          <MCPServersPanel />
        </section>
      </div>
    </ErrorBoundary>
  )
}
