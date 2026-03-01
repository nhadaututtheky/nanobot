import { useState } from 'react'
import { Settings } from 'lucide-react'
import { toast } from 'sonner'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { rpc } from '@/ws/rpc'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetFooter,
  SheetTrigger,
} from '@/components/ui/sheet'
import { formatCompact, formatRelativeTime } from '@/lib/utils'

interface SessionMetaProps {
  sessionKey: string
  label?: string
  thinkingLevel?: string
}

interface UsageData {
  totalTokens?: number
  inputTokens?: number
  outputTokens?: number
}

interface SessionData {
  key: string
  label?: string
  createdAt?: string
  updatedAt?: string
  lastActiveAt?: string
}

const THINKING_LEVELS = [
  { value: 'none', label: 'None' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
] as const

export function SessionMeta({ sessionKey, label, thinkingLevel }: SessionMetaProps) {
  const [open, setOpen] = useState(false)
  const [labelValue, setLabelValue] = useState(label ?? '')
  const [thinkingValue, setThinkingValue] = useState(thinkingLevel ?? 'none')
  const [saving, setSaving] = useState(false)
  const queryClient = useQueryClient()

  const { data: usageData, isLoading: usageLoading } = useQuery({
    queryKey: ['sessions', 'usage', sessionKey],
    queryFn: () => rpc.sessions.usage({ sessionKey }),
    enabled: open && Boolean(sessionKey),
  })

  const { data: sessionsData } = useQuery({
    queryKey: ['sessions'],
    enabled: open,
  })

  const sessions = (sessionsData as SessionData[] | undefined) ?? []
  const sessionInfo = sessions.find((s) => s.key === sessionKey)

  const usage = usageData as UsageData | undefined
  const totalTokens = usage?.totalTokens

  async function handleSave() {
    setSaving(true)
    try {
      await rpc.sessions.patch({
        sessionKey,
        updates: {
          label: labelValue || undefined,
          thinkingLevel: thinkingValue,
        },
      })
      toast.success('Session updated')
      void queryClient.invalidateQueries({ queryKey: ['sessions'] })
      setOpen(false)
    } catch (err) {
      toast.error('Failed to update session', {
        description: err instanceof Error ? err.message : 'Unknown error',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          size="icon"
          variant="ghost"
          aria-label="Session settings"
          className="h-8 w-8"
        >
          <Settings className="h-4 w-4" aria-hidden="true" />
        </Button>
      </SheetTrigger>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Session Settings</SheetTitle>
        </SheetHeader>
        <div className="flex flex-col gap-4 p-4">
          {/* Session key */}
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Session Key</p>
            <p className="break-all font-mono text-xs">{sessionKey}</p>
          </div>

          {/* Dates */}
          {sessionInfo && (
            <div className="grid grid-cols-2 gap-3">
              {sessionInfo.createdAt && (
                <div className="space-y-0.5">
                  <p className="text-xs font-medium text-muted-foreground">Created</p>
                  <p className="text-xs">{formatRelativeTime(sessionInfo.createdAt)}</p>
                </div>
              )}
              {(sessionInfo.updatedAt ?? sessionInfo.lastActiveAt) && (
                <div className="space-y-0.5">
                  <p className="text-xs font-medium text-muted-foreground">Last active</p>
                  <p className="text-xs">
                    {formatRelativeTime(
                      (sessionInfo.updatedAt ?? sessionInfo.lastActiveAt)!,
                    )}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Token usage badge */}
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Token Usage</p>
            {usageLoading ? (
              <Skeleton className="h-5 w-24 rounded-full" />
            ) : totalTokens !== undefined ? (
              <Badge variant="outline" className="font-mono text-xs">
                {formatCompact(totalTokens)} tokens
                {usage?.inputTokens !== undefined && (
                  <span className="text-muted-foreground">
                    {' '}({formatCompact(usage.inputTokens ?? 0)}↑ {formatCompact(usage.outputTokens ?? 0)}↓)
                  </span>
                )}
              </Badge>
            ) : (
              <p className="text-xs text-muted-foreground">No usage data</p>
            )}
          </div>

          {/* Label */}
          <div className="space-y-1.5">
            <Label htmlFor="session-label">Label</Label>
            <Input
              id="session-label"
              value={labelValue}
              onChange={(e) => setLabelValue(e.target.value)}
              placeholder="Custom display name…"
            />
          </div>

          {/* Thinking level */}
          <div className="space-y-1.5">
            <Label htmlFor="thinking-level">Thinking Level</Label>
            <Select value={thinkingValue} onValueChange={setThinkingValue}>
              <SelectTrigger id="thinking-level">
                <SelectValue placeholder="Select level" />
              </SelectTrigger>
              <SelectContent>
                {THINKING_LEVELS.map((level) => (
                  <SelectItem key={level.value} value={level.value}>
                    {level.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <SheetFooter>
          <Button onClick={() => void handleSave()} disabled={saving} className="w-full">
            {saving ? 'Saving…' : 'Save changes'}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
