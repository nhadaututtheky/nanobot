import { useState, useCallback } from 'react'
import { Plus, Clock } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { rpc } from '@/ws/rpc'
import { useEvent } from '@/ws/provider'
import { PageHeader } from '@/components/common/PageHeader'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { CronJobList } from './CronJobList'
import { CronJobForm } from './CronJobForm'
import { CronRunHistory } from './CronRunHistory'

// ---------------------------------------------------------------------------
// CronServiceStatus badge
// ---------------------------------------------------------------------------

interface CronStatus {
  running: boolean
  jobCount: number
  nextRunIn?: number
}

function CronServiceBadge() {
  const { data, isLoading } = useQuery({
    queryKey: ['cron-status'],
    queryFn: () => rpc.cron.status(),
    select: (d) => d as CronStatus,
    refetchInterval: 15_000,
  })

  if (isLoading) return <Skeleton className="h-5 w-20" />

  return (
    <div className="flex items-center gap-2">
      <Clock className="h-4 w-4 text-muted-foreground" />
      <Badge
        variant="outline"
        className={
          data?.running
            ? 'border-success text-success'
            : 'border-destructive text-destructive'
        }
      >
        {data?.running ? 'Running' : 'Stopped'}
      </Badge>
      {data?.jobCount !== undefined && (
        <span className="text-xs text-muted-foreground">
          {data.jobCount} job{data.jobCount !== 1 ? 's' : ''}
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// CronPage
// ---------------------------------------------------------------------------

export function CronPage() {
  const [formOpen, setFormOpen] = useState(false)
  const queryClient = useQueryClient()

  useEvent(
    'cron',
    useCallback(() => {
      void queryClient.invalidateQueries({ queryKey: ['cron-list'] })
      void queryClient.invalidateQueries({ queryKey: ['cron-status'] })
      void queryClient.invalidateQueries({ queryKey: ['cron-runs'] })
    }, [queryClient]),
  )

  return (
    <ErrorBoundary>
      <PageHeader
        title="Cron Jobs"
        description="Scheduled tasks and automation"
        actions={
          <div className="flex items-center gap-3">
            <CronServiceBadge />
            <Button size="sm" onClick={() => setFormOpen(true)}>
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Add Job
            </Button>
          </div>
        }
      />

      <div className="space-y-6">
        <CronJobList />
        <CronRunHistory />
      </div>

      <CronJobForm open={formOpen} onOpenChange={setFormOpen} />
    </ErrorBoundary>
  )
}
