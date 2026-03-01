import { useState, useCallback } from 'react'
import { Activity, MessageSquare, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useEvent } from '@/ws/provider'
import { formatRelativeTime } from '@/lib/utils'
import { cn } from '@/lib/utils'

interface FeedItem {
  id: string
  sessionKey: string
  state: string
  timestamp: Date
}

const stateIcons = {
  started: <Loader2 className="h-3.5 w-3.5 animate-spin text-info" />,
  done: <CheckCircle2 className="h-3.5 w-3.5 text-success" />,
  error: <XCircle className="h-3.5 w-3.5 text-destructive" />,
  aborted: <XCircle className="h-3.5 w-3.5 text-warning" />,
  delta: <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />,
} as const

export function ActivityFeed() {
  const [items, setItems] = useState<FeedItem[]>([])

  useEvent('chat', useCallback((payload: unknown) => {
    const p = payload as Record<string, unknown>
    const state = p['state'] as string
    if (state === 'delta') return // skip deltas in feed

    const item: FeedItem = {
      id: `${p['runId'] ?? ''}-${state}-${Date.now()}`,
      sessionKey: (p['sessionKey'] as string) ?? 'unknown',
      state,
      timestamp: new Date(),
    }

    setItems((prev) => [item, ...prev].slice(0, 20))
  }, []))

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-4 w-4" />
          Activity Feed
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-64">
          {items.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No activity yet. Events will appear here in real-time.
            </p>
          ) : (
            <div className="space-y-2">
              {items.map((item) => (
                <div
                  key={item.id}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm',
                    'border border-transparent hover:border-border hover:bg-muted/50',
                  )}
                >
                  {stateIcons[item.state as keyof typeof stateIcons] ?? (
                    <Activity className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                  <span className="min-w-0 flex-1 truncate font-mono text-xs">
                    {item.sessionKey}
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formatRelativeTime(item.timestamp)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
