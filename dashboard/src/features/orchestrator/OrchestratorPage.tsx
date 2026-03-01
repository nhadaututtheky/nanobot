import { useState, useCallback } from 'react'
import { Network, ChevronRight } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/common/PageHeader'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import type { GraphSummary, TaskGraph } from '@/types/orchestrator'
import { GoalInput } from './GoalInput'
import { OrchestratorSettings } from './OrchestratorSettings'
import { TaskGraphView } from './TaskGraphView'
import {
  useGraphList,
  useRunGoal,
  useDecomposeGoal,
  useOrchestratorEvents,
} from './useOrchestrator'

// ---------------------------------------------------------------------------
// Status colour helpers
// ---------------------------------------------------------------------------

const STATUS_DOT: Record<string, string> = {
  draft: 'bg-muted-foreground',
  running: 'bg-primary animate-pulse',
  completed: 'bg-success',
  failed: 'bg-destructive',
  cancelled: 'bg-muted-foreground',
}

// ---------------------------------------------------------------------------
// Graph list item
// ---------------------------------------------------------------------------

function GraphListItem({
  graph,
  selected,
  onClick,
}: {
  graph: GraphSummary
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-3 rounded-lg border border-border p-3 text-left transition-colors',
        'hover:border-primary/30 cursor-pointer',
        selected && 'border-primary/50 bg-primary/5',
      )}
    >
      <span className={cn('h-2 w-2 rounded-full shrink-0', STATUS_DOT[graph.status])} />

      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium truncate">{graph.goal}</p>
        <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
          <span>{graph.nodeCount} tasks</span>
          <span>{Math.round(graph.progress * 100)}%</span>
          <Badge variant="outline" className="text-[9px] px-1 py-0">
            {graph.status}
          </Badge>
        </div>
      </div>

      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </button>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function OrchestratorPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: graphs, isLoading } = useGraphList()
  const runMut = useRunGoal()
  const decomposeMut = useDecomposeGoal()

  // Real-time updates
  useOrchestratorEvents()

  const handleRun = useCallback(
    (goal: string, context: string) => {
      runMut.mutate(
        { goal, context: context || undefined },
        {
          onSuccess: (data) => {
            const graph = data as TaskGraph
            setSelectedId(graph.id)
            toast.success('Orchestrator started')
          },
          onError: (err) => {
            toast.error(`Failed: ${err.message}`)
          },
        },
      )
    },
    [runMut],
  )

  const handleDecompose = useCallback(
    (goal: string, context: string) => {
      decomposeMut.mutate(
        { goal, context: context || undefined },
        {
          onSuccess: (data) => {
            const graph = data as TaskGraph
            setSelectedId(graph.id)
            toast.success(`Decomposed into ${graph.nodes.length} tasks (preview)`)
          },
          onError: (err) => {
            toast.error(`Failed: ${err.message}`)
          },
        },
      )
    },
    [decomposeMut],
  )

  return (
    <ErrorBoundary>
      <PageHeader
        title="Orchestrator"
        description="Multi-model task graph execution"
        actions={
          <div className="flex items-center gap-2">
            <Network className="h-4 w-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">
              {graphs?.length ?? 0} graph{(graphs?.length ?? 0) !== 1 ? 's' : ''}
            </span>
          </div>
        }
      />

      <div className="space-y-6">
        {/* Goal input */}
        <GoalInput
          onRun={handleRun}
          onDecompose={handleDecompose}
          isRunning={runMut.isPending}
          isDecomposing={decomposeMut.isPending}
        />

        {/* Selected graph detail */}
        {selectedId && (
          <TaskGraphView graphId={selectedId} onClose={() => setSelectedId(null)} />
        )}

        {/* Graph list */}
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-muted-foreground">Recent Graphs</h3>

          {isLoading && (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          )}

          {!isLoading && graphs?.length === 0 && (
            <p className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              No graphs yet. Enter a goal above to get started.
            </p>
          )}

          {graphs?.map((g) => (
            <GraphListItem
              key={g.id}
              graph={g}
              selected={g.id === selectedId}
              onClick={() => setSelectedId(g.id === selectedId ? null : g.id)}
            />
          ))}
        </div>

        {/* Telegram integration settings */}
        <OrchestratorSettings />
      </div>
    </ErrorBoundary>
  )
}
