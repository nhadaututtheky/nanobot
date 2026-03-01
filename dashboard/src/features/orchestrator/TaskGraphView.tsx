import { useMemo } from 'react'
import {
  XCircle,
  RefreshCw,
  Trash2,
  Play,
  Loader2,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { TaskGraph, TaskNode } from '@/types/orchestrator'
import { TaskNodeCard } from './TaskNodeCard'
import {
  useGraph,
  useCancelGraph,
  useRetryGraph,
  useDeleteGraph,
  useExecuteGraph,
} from './useOrchestrator'

// ---------------------------------------------------------------------------
// Wave computation (group tasks by execution order)
// ---------------------------------------------------------------------------

function computeWaves(graph: TaskGraph): TaskNode[][] {
  const nodeMap = new Map(graph.nodes.map((n) => [n.id, n]))
  const inDegree = new Map(graph.nodes.map((n) => [n.id, 0]))
  const adj = new Map<string, string[]>()

  for (const edge of graph.edges) {
    inDegree.set(edge.toId, (inDegree.get(edge.toId) ?? 0) + 1)
    // Build adjacency without mutating shared arrays
    adj.set(edge.fromId, [...(adj.get(edge.fromId) ?? []), edge.toId])
  }

  const waves: TaskNode[][] = []
  let queue = graph.nodes.filter((n) => (inDegree.get(n.id) ?? 0) === 0)
  let visited = 0

  while (queue.length > 0) {
    waves.push(queue)
    visited += queue.length
    // Cycle guard — if visited exceeds node count something is wrong
    if (visited > graph.nodes.length) break
    const next: TaskNode[] = []
    for (const node of queue) {
      for (const dep of adj.get(node.id) ?? []) {
        const newDeg = (inDegree.get(dep) ?? 1) - 1
        inDegree.set(dep, newDeg)
        if (newDeg === 0) {
          const n = nodeMap.get(dep)
          if (n) next.push(n)
        }
      }
    }
    queue = next
  }

  return waves
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_STYLES: Record<string, string> = {
  draft: 'border-muted-foreground text-muted-foreground',
  running: 'border-primary text-primary',
  completed: 'border-success text-success',
  failed: 'border-destructive text-destructive',
  cancelled: 'border-muted-foreground text-muted-foreground',
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface TaskGraphViewProps {
  graphId: string
  onClose: () => void
}

export function TaskGraphView({ graphId, onClose }: TaskGraphViewProps) {
  const { data: graph, isLoading, error } = useGraph(graphId)
  const cancelMut = useCancelGraph()
  const retryMut = useRetryGraph()
  const deleteMut = useDeleteGraph()
  const executeMut = useExecuteGraph()

  const waves = useMemo(() => (graph ? computeWaves(graph) : []), [graph])

  // Build label map for dependency display
  const labelMap = useMemo(() => {
    if (!graph) return new Map<string, string>()
    return new Map(graph.nodes.map((n) => [n.id, n.label]))
  }, [graph])

  const depEdges = useMemo(() => {
    if (!graph) return new Map<string, string[]>()
    const m = new Map<string, string[]>()
    for (const e of graph.edges) {
      m.set(e.toId, [...(m.get(e.toId) ?? []), e.fromId])
    }
    return m
  }, [graph])

  if (isLoading) {
    return (
      <div className="space-y-4 rounded-lg border border-border bg-card p-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    )
  }

  if (!graph) {
    return (
      <div className="rounded-lg border border-border bg-card p-6 text-center text-muted-foreground">
        {error ? `Failed to load graph: ${error.message}` : 'Graph not found.'}
      </div>
    )
  }

  const isRunning = graph.status === 'running'
  const isTerminal = ['completed', 'failed', 'cancelled'].includes(graph.status)
  const hasFailed = graph.nodes.some((n) => n.status === 'failed' || n.status === 'skipped')

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold truncate">{graph.goal}</h3>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span className="font-mono">{graph.id}</span>
            <Badge variant="outline" className={cn('text-[10px]', STATUS_STYLES[graph.status])}>
              {graph.status}
            </Badge>
            <span>{graph.nodes.length} tasks</span>
            <span>{Math.round(graph.progress * 100)}%</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          {graph.status === 'draft' && (
            <Button
              variant="outline"
              size="sm"
              aria-label="Execute graph"
              onClick={() => executeMut.mutate(graph.id)}
              disabled={executeMut.isPending}
            >
              {executeMut.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <Play className="h-3.5 w-3.5" aria-hidden="true" />
              )}
            </Button>
          )}
          {isRunning && (
            <Button
              variant="outline"
              size="sm"
              aria-label="Cancel graph"
              onClick={() => cancelMut.mutate(graph.id)}
              disabled={cancelMut.isPending}
            >
              <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          )}
          {isTerminal && hasFailed && (
            <Button
              variant="outline"
              size="sm"
              aria-label="Retry failed tasks"
              onClick={() => retryMut.mutate(graph.id)}
              disabled={retryMut.isPending}
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          )}
          {isTerminal && (
            <Button
              variant="ghost"
              size="sm"
              aria-label="Delete graph"
              onClick={() => deleteMut.mutate(graph.id, { onSuccess: onClose })}
              disabled={deleteMut.isPending}
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          )}
        </div>
      </div>

      {/* Progress bar */}
      {isRunning && (
        <div className="h-1.5 w-full rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${Math.round(graph.progress * 100)}%` }}
          />
        </div>
      )}

      {/* Waves */}
      <div className="space-y-3">
        {waves.map((wave, i) => (
          <div key={wave.map((n) => n.id).join(',') || i}>
            <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Wave {i + 1}
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {wave.map((node) => (
                <TaskNodeCard
                  key={node.id}
                  node={node}
                  dependencyLabels={
                    (depEdges.get(node.id) ?? [])
                      .map((id) => labelMap.get(id) ?? id)
                  }
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
