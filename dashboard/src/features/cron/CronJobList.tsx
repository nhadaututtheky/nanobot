import { useState } from 'react'
import { Play, Trash2, Loader2 } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { rpc } from '@/ws/rpc'
import { Card, CardContent } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { formatRelativeTime } from '@/lib/utils'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CronJob {
  jobId: string
  expression: string
  task: string
  enabled: boolean
  lastRun?: string
  sessionKey?: string
}

// ---------------------------------------------------------------------------
// CronJobList
// ---------------------------------------------------------------------------

export function CronJobList() {
  const queryClient = useQueryClient()
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['cron-list'],
    queryFn: () => rpc.cron.list(),
    select: (d) => d as CronJob[],
    refetchInterval: 30_000,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ jobId, enabled }: { jobId: string; enabled: boolean }) =>
      rpc.cron.update({ jobId, enabled }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['cron-list'] }),
    onError: () => toast.error('Failed to update job'),
  })

  const runMutation = useMutation({
    mutationFn: (jobId: string) => rpc.cron.run({ jobId }),
    onSuccess: () => {
      toast.success('Job triggered')
      void queryClient.invalidateQueries({ queryKey: ['cron-list'] })
      void queryClient.invalidateQueries({ queryKey: ['cron-runs'] })
    },
    onError: () => toast.error('Failed to run job'),
  })

  const deleteMutation = useMutation({
    mutationFn: (jobId: string) => rpc.cron.remove({ jobId }),
    onSuccess: () => {
      toast.success('Job removed')
      void queryClient.invalidateQueries({ queryKey: ['cron-list'] })
    },
    onError: () => toast.error('Failed to remove job'),
  })

  if (isLoading) {
    return (
      <Card>
        <CardContent className="pt-4 space-y-3">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (!data || data.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-sm text-muted-foreground">No cron jobs configured.</p>
          <p className="mt-1 text-xs text-muted-foreground">Add a job to schedule automated tasks.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <Card>
        <CardContent className="pt-0 p-0">
          <div className="divide-y divide-border overflow-hidden rounded-lg">
            <div className="hidden sm:grid sm:grid-cols-[1fr_auto_auto_auto_auto] gap-3 items-center px-4 py-2 text-xs font-medium text-muted-foreground bg-muted/30">
              <span>Job</span>
              <span className="text-center">Enabled</span>
              <span>Last Run</span>
              <span className="sr-only">Actions</span>
            </div>
            {data.map((job) => (
              <div
                key={job.jobId}
                className={cn(
                  'grid grid-cols-[1fr_auto] gap-3 items-center px-4 py-3',
                  'sm:grid-cols-[1fr_auto_auto_auto_auto]',
                  'hover:bg-muted/20 transition-colors',
                )}
              >
                {/* Info */}
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-xs bg-muted/60 px-1.5 py-0.5 rounded text-muted-foreground">
                      {job.expression}
                    </span>
                    {job.sessionKey && (
                      <Badge variant="outline" className="text-xs">
                        {job.sessionKey}
                      </Badge>
                    )}
                  </div>
                  <p className="mt-0.5 truncate text-sm text-foreground">{job.task}</p>
                </div>

                {/* Toggle */}
                <Switch
                  checked={job.enabled}
                  onCheckedChange={(enabled) =>
                    toggleMutation.mutate({ jobId: job.jobId, enabled })
                  }
                  disabled={toggleMutation.isPending}
                  aria-label={`Toggle ${job.task}`}
                  className="hidden sm:flex"
                />

                {/* Last run */}
                <span className="hidden sm:block text-xs text-muted-foreground whitespace-nowrap">
                  {job.lastRun ? formatRelativeTime(job.lastRun) : 'Never'}
                </span>

                {/* Actions */}
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    aria-label="Run now"
                    onClick={() => runMutation.mutate(job.jobId)}
                    disabled={runMutation.isPending}
                  >
                    {runMutation.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Play className="h-3.5 w-3.5" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive hover:text-destructive"
                    aria-label="Delete job"
                    onClick={() => setDeletingId(job.jobId)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <AlertDialog open={!!deletingId} onOpenChange={(o) => !o && setDeletingId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove cron job?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. The scheduled job will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (deletingId) {
                  deleteMutation.mutate(deletingId)
                  setDeletingId(null)
                }
              }}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
