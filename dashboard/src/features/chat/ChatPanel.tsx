import { useEffect, useRef, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, MessageSquare } from 'lucide-react'
import { toast } from 'sonner'
import { rpc } from '@/ws/rpc'
import { useEvent } from '@/ws/provider'
import { useChatStore } from '@/stores/useChatStore'
import { ChatBubble } from '@/components/ChatBubble'
import { ChatInput } from '@/components/ChatInput'
import { EmptyState } from '@/components/common/EmptyState'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { TokenUsageBadge } from './TokenUsageBadge'
import { SessionMeta } from './SessionMeta'

interface HistoryMessage {
  id?: string
  role: 'user' | 'assistant' | 'context' | 'system'
  content: string
  timestamp?: string
}

interface ChatBroadcast {
  state: string
  sessionKey?: string
  runId?: string
  delta?: string
  error?: string
}

interface ChatPanelProps {
  sessionKey: string | null
}

function MessageSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <div className="flex justify-end">
        <Skeleton className="h-12 w-48 rounded-xl" />
      </div>
      <div className="flex justify-start">
        <Skeleton className="h-20 w-64 rounded-xl" />
      </div>
      <div className="flex justify-end">
        <Skeleton className="h-10 w-36 rounded-xl" />
      </div>
    </div>
  )
}

export function ChatPanel({ sessionKey }: ChatPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()
  const isStreaming = useChatStore((s) => s.isStreaming)
  const activeRunId = useChatStore((s) => s.activeRunId)
  const startStreaming = useChatStore((s) => s.startStreaming)
  const appendDelta = useChatStore((s) => s.appendDelta)
  const stopStreaming = useChatStore((s) => s.stopStreaming)
  const clearStream = useChatStore((s) => s.clearStream)
  const getStreamContent = useChatStore((s) => s.getStreamContent)

  const { data, isLoading } = useQuery({
    queryKey: ['chat', 'history', sessionKey],
    queryFn: () => rpc.chat.history({ sessionKey: sessionKey! }),
    enabled: Boolean(sessionKey),
  })

  const raw = data as { messages?: HistoryMessage[] } | HistoryMessage[] | undefined
  const messages = Array.isArray(raw) ? raw : (raw?.messages ?? [])

  // Auto-scroll to bottom on new messages or streaming
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, isStreaming])

  useEvent(
    'chat',
    useCallback(
      (payload: unknown) => {
        const p = payload as ChatBroadcast

        // Only handle events for the active session
        if (sessionKey && p.sessionKey && p.sessionKey !== sessionKey) return

        if (p.state === 'started' && p.runId) {
          startStreaming(p.runId)
        } else if (p.state === 'delta' && p.runId && p.delta) {
          appendDelta(p.runId, p.delta)
          bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
        } else if (p.state === 'done') {
          if (p.runId) clearStream(p.runId)
          stopStreaming()
          void queryClient.invalidateQueries({
            queryKey: ['chat', 'history', sessionKey],
          })
          void queryClient.invalidateQueries({ queryKey: ['sessions'] })
        } else if (p.state === 'error') {
          stopStreaming()
          if (p.runId) clearStream(p.runId)
          toast.error('Response error', {
            description: p.error ?? 'An error occurred during generation.',
          })
        } else if (p.state === 'aborted') {
          stopStreaming()
          if (p.runId) clearStream(p.runId)
          toast.warning('Generation stopped')
        }
      },
      [sessionKey, startStreaming, appendDelta, stopStreaming, clearStream, queryClient],
    ),
  )

  if (!sessionKey) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon={<MessageSquare className="h-10 w-10" />}
          title="No session selected"
          description="Select a session from the list to view its conversation."
        />
      </div>
    )
  }

  const streamContent = activeRunId ? getStreamContent(activeRunId) : ''

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="truncate font-mono text-sm font-medium">{sessionKey}</span>
          <TokenUsageBadge sessionKey={sessionKey} />
        </div>
        <SessionMeta sessionKey={sessionKey} />
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 min-h-0">
        {isLoading ? (
          <MessageSkeleton />
        ) : messages.length === 0 && !isStreaming ? (
          <EmptyState
            className="h-full"
            icon={<MessageSquare className="h-8 w-8" />}
            title="No messages yet"
            description="Send a message to start the conversation."
          />
        ) : (
          <div className="space-y-3 p-4">
            {messages.map((msg, i) => (
              <ChatBubble
                key={msg.id ?? i}
                role={msg.role}
                content={msg.content}
                timestamp={msg.timestamp}
              />
            ))}
            {isStreaming && activeRunId && streamContent && (
              <ChatBubble role="assistant" content={streamContent} />
            )}
            {isStreaming && (!activeRunId || !streamContent) && (
              <div className="flex items-center gap-2 px-2 text-sm text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                <span>Thinking…</span>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </ScrollArea>

      {/* Input */}
      <ChatInput sessionKey={sessionKey} />
    </div>
  )
}
