import { useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { MessageSquare, Trash2, Search } from 'lucide-react'
import { toast } from 'sonner'
import { rpc } from '@/ws/rpc'
import { useEvent } from '@/ws/provider'
import { useChatStore } from '@/stores/useChatStore'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { formatRelativeTime } from '@/lib/utils'

interface Session {
  key: string
  label?: string
  channelId?: string
  lastActiveAt?: string
  messageCount?: number
}

function SessionSkeleton() {
  return (
    <div className="space-y-2 p-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full rounded-lg" />
      ))}
    </div>
  )
}

interface SessionItemProps {
  session: Session
  isActive: boolean
  onSelect: (key: string) => void
  onDelete: (key: string) => void
}

function SessionItem({ session, isActive, onSelect, onDelete }: SessionItemProps) {
  const displayName = session.label ?? session.key
  const lastActive = session.lastActiveAt
    ? formatRelativeTime(session.lastActiveAt)
    : null

  return (
    <div
      className={cn(
        'group flex cursor-pointer items-start gap-2 rounded-lg px-3 py-2.5 transition-colors hover:bg-accent',
        isActive && 'bg-accent',
      )}
      onClick={() => onSelect(session.key)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onSelect(session.key)
      }}
      aria-selected={isActive}
    >
      <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{displayName}</p>
        <div className="flex items-center gap-2">
          {session.channelId && (
            <span className="truncate font-mono text-xs text-muted-foreground">
              {session.channelId}
            </span>
          )}
          {lastActive && (
            <span className="shrink-0 text-xs text-muted-foreground">{lastActive}</span>
          )}
        </div>
        {session.messageCount !== undefined && (
          <span className="text-xs text-muted-foreground">
            {session.messageCount} messages
          </span>
        )}
      </div>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
            aria-label={`Delete session ${displayName}`}
            onClick={(e) => e.stopPropagation()}
          >
            <Trash2 className="h-3.5 w-3.5 text-destructive" aria-hidden="true" />
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete session?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete "{displayName}" and all its messages.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => onDelete(session.key)}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export function SessionList() {
  const [search, setSearch] = useState('')
  const activeSessionKey = useChatStore((s) => s.activeSessionKey)
  const setActiveSession = useChatStore((s) => s.setActiveSession)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => rpc.sessions.list(),
  })

  // Refresh on chat broadcast events
  useEvent('chat', useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['sessions'] })
  }, [queryClient]))

  const raw = data as { sessions?: Session[] } | Session[] | undefined
  const sessions = Array.isArray(raw) ? raw : (raw?.sessions ?? [])

  const filtered = search
    ? sessions.filter(
        (s) =>
          s.key.toLowerCase().includes(search.toLowerCase()) ||
          (s.label ?? '').toLowerCase().includes(search.toLowerCase()),
      )
    : sessions

  function handleSelect(key: string) {
    setActiveSession(key)
    navigate(`/chat/${encodeURIComponent(key)}`)
  }

  async function handleDelete(key: string) {
    try {
      await rpc.sessions.delete({ sessionKey: key })
      toast.success('Session deleted')
      if (activeSessionKey === key) {
        setActiveSession(null)
        navigate('/chat')
      }
      void queryClient.invalidateQueries({ queryKey: ['sessions'] })
    } catch (err) {
      toast.error('Failed to delete session', {
        description: err instanceof Error ? err.message : 'Unknown error',
      })
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col border-r">
      <div className="border-b p-3">
        <div className="relative">
          <Search
            className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            placeholder="Search sessions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 text-sm"
            aria-label="Search sessions"
          />
        </div>
      </div>
      <ScrollArea className="flex-1 min-h-0">
        {isLoading ? (
          <SessionSkeleton />
        ) : filtered.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {search ? 'No sessions match your search.' : 'No sessions yet.'}
          </p>
        ) : (
          <div className="p-2 space-y-0.5">
            {filtered.map((session) => (
              <SessionItem
                key={session.key}
                session={session}
                isActive={activeSessionKey === session.key}
                onSelect={handleSelect}
                onDelete={(key) => void handleDelete(key)}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
