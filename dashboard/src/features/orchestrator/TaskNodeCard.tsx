import {
  Brain,
  Code,
  Search,
  Palette,
  BarChart3,
  Languages,
  FileText,
  Bot,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  SkipForward,
  Ban,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import type { TaskNode, TaskCapability, TaskStatus } from '@/types/orchestrator'
import { useState } from 'react'

// ---------------------------------------------------------------------------
// Icons / colours
// ---------------------------------------------------------------------------

const CAPABILITY_META: Record<TaskCapability, { icon: typeof Brain; label: string; color: string }> = {
  reasoning: { icon: Brain, label: 'Reasoning', color: 'text-purple-400' },
  coding: { icon: Code, label: 'Coding', color: 'text-blue-400' },
  research: { icon: Search, label: 'Research', color: 'text-emerald-400' },
  creative: { icon: Palette, label: 'Creative', color: 'text-pink-400' },
  data_analysis: { icon: BarChart3, label: 'Analysis', color: 'text-amber-400' },
  translation: { icon: Languages, label: 'Translation', color: 'text-cyan-400' },
  summarization: { icon: FileText, label: 'Summary', color: 'text-orange-400' },
  general: { icon: Bot, label: 'General', color: 'text-muted-foreground' },
}

const STATUS_META: Record<TaskStatus, { icon: typeof Clock; color: string; bg: string }> = {
  pending: { icon: Clock, color: 'text-muted-foreground', bg: 'bg-muted/30' },
  queued: { icon: Clock, color: 'text-blue-400', bg: 'bg-blue-500/10' },
  running: { icon: Loader2, color: 'text-primary', bg: 'bg-primary/10' },
  completed: { icon: CheckCircle2, color: 'text-success', bg: 'bg-success/10' },
  failed: { icon: XCircle, color: 'text-destructive', bg: 'bg-destructive/10' },
  cancelled: { icon: Ban, color: 'text-muted-foreground', bg: 'bg-muted/20' },
  skipped: { icon: SkipForward, color: 'text-muted-foreground', bg: 'bg-muted/20' },
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface TaskNodeCardProps {
  node: TaskNode
  dependencyLabels?: string[]
}

export function TaskNodeCard({ node, dependencyLabels }: TaskNodeCardProps) {
  const [expanded, setExpanded] = useState(false)
  const cap = CAPABILITY_META[node.capability] ?? CAPABILITY_META.general
  const status = STATUS_META[node.status] ?? STATUS_META.pending
  const CapIcon = cap.icon
  const StatusIcon = status.icon

  const modelShort = node.assignedModel.split('/').pop() ?? node.assignedModel
  const detailId = `node-detail-${node.id}`

  return (
    <button
      type="button"
      onClick={() => setExpanded(!expanded)}
      aria-expanded={expanded}
      aria-controls={detailId}
      className={cn(
        'w-full rounded-lg border border-border p-3 text-left transition-colors',
        status.bg,
        'hover:border-primary/30 cursor-pointer',
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-2">
        <StatusIcon
          aria-hidden="true"
          className={cn('mt-0.5 h-4 w-4 shrink-0', status.color, node.status === 'running' && 'animate-spin')}
        />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium truncate">{node.label}</span>
            <Badge variant="outline" className={cn('shrink-0 text-[10px] px-1.5 py-0', cap.color)}>
              <CapIcon className="mr-1 h-3 w-3" aria-hidden="true" />
              {cap.label}
            </Badge>
          </div>

          <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
            <span className="font-mono">{modelShort}</span>
            {dependencyLabels && dependencyLabels.length > 0 && (
              <span>after: {dependencyLabels.join(', ')}</span>
            )}
          </div>

          {/* Progress bar for running tasks */}
          {node.status === 'running' && node.progress > 0 && (
            <div className="mt-2 h-1 w-full rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${Math.round(node.progress * 100)}%` }}
              />
            </div>
          )}
        </div>
      </div>

      {/* Expanded: result or error */}
      {expanded && (
        <div id={detailId} className="mt-3 border-t border-border pt-2">
          {node.description && (
            <p className="text-xs text-muted-foreground mb-2">{node.description}</p>
          )}
          {node.error && (
            <p className="text-xs text-destructive font-mono whitespace-pre-wrap">
              {node.error}
            </p>
          )}
          {node.outputSummary && (
            <p className="text-xs text-foreground/80 font-mono whitespace-pre-wrap max-h-40 overflow-auto">
              {node.outputSummary}
            </p>
          )}
          {!node.error && !node.outputSummary && node.status === 'pending' && (
            <p className="text-xs text-muted-foreground italic">Waiting for dependencies...</p>
          )}
        </div>
      )}
    </button>
  )
}
