import { useState } from 'react'
import { ChevronDown, ChevronRight, History } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { rpc } from '@/ws/rpc'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { formatRelativeTime } from '@/lib/utils'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CronRun {
  runId: string
  jobId: string
  status: string
  startedAt: string
  durationMs?: number
  response?: string
}

interface CronRunHistoryProps {
  jobId?: string
}

// ---------------------------------------------------------------------------
// CronRunHistory
// ---------------------------------------------------------------------------

export function CronRunHistory({ jobId }: CronRunHistoryProps) {
  const [open, setOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['cron-runs', jobId],
    queryFn: () => rpc.cron.runs({ jobId, limit: 20 }),
    enabled: open,
    select: (d) => {
      const raw = d as { runs?: CronRun[] } | CronRun[]
      return Array.isArray(raw) ? raw : (raw.runs ?? [])
    },
  })

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card>
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer select-none py-3 hover:bg-muted/30 transition-colors rounded-t-lg">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold">
              <History className="h-4 w-4" />
              Run History
              <span className="ml-auto text-muted-foreground">
                {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </span>
            </CardTitle>
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="pt-0">
            {isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : !data || data.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">No runs yet</p>
            ) : (
              <div className="divide-y divide-border">
                {data.map((run) => (
                  <div
                    key={run.runId}
                    className="flex items-center gap-3 py-2.5 text-sm"
                  >
                    <RunStatusBadge status={run.status} />
                    <span className="font-mono text-xs text-muted-foreground">
                      {formatRelativeTime(run.startedAt)}
                    </span>
                    {run.durationMs !== undefined && (
                      <span className={cn('font-mono text-xs', 'text-muted-foreground')}>
                        {run.durationMs}ms
                      </span>
                    )}
                    {run.response && (
                      <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                        {run.response}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}

// ---------------------------------------------------------------------------
// RunStatusBadge
// ---------------------------------------------------------------------------

function RunStatusBadge({ status }: { status: string }) {
  const variants: Record<string, string> = {
    success: 'border-success text-success',
    error: 'border-destructive text-destructive',
    running: 'border-info text-info',
  }
  const cls = variants[status] ?? 'border-muted-foreground text-muted-foreground'

  return (
    <Badge variant="outline" className={cn('text-xs capitalize', cls)}>
      {status}
    </Badge>
  )
}
