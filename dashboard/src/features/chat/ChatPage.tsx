import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { useChatStore } from '@/stores/useChatStore'
import { SessionList } from './SessionList'
import { ChatPanel } from './ChatPanel'

export function ChatPage() {
  const { sessionKey } = useParams<{ sessionKey?: string }>()
  const activeSessionKey = useChatStore((s) => s.activeSessionKey)
  const setActiveSession = useChatStore((s) => s.setActiveSession)

  // Sync URL param into store on mount / param change
  useEffect(() => {
    const decoded = sessionKey ? decodeURIComponent(sessionKey) : null
    if (decoded !== activeSessionKey) {
      setActiveSession(decoded)
    }
  }, [sessionKey, activeSessionKey, setActiveSession])

  const resolvedKey = sessionKey ? decodeURIComponent(sessionKey) : null

  return (
    <ErrorBoundary>
      {/* Full-height split layout — no PageHeader to maximize vertical space */}
      <div className="flex h-[calc(100vh-4rem)] overflow-hidden rounded-xl border">
        {/* Session list — fixed 280px on desktop, full width stacked on mobile */}
        <div className="hidden w-[280px] shrink-0 md:flex md:flex-col">
          <SessionList />
        </div>

        {/* Mobile: session list above, panel below */}
        <div className="flex flex-1 flex-col md:hidden">
          {resolvedKey ? (
            <ChatPanel sessionKey={resolvedKey} />
          ) : (
            <div className="flex flex-col">
              <SessionList />
            </div>
          )}
        </div>

        {/* Desktop: chat panel */}
        <div className="hidden flex-1 flex-col md:flex">
          <ChatPanel sessionKey={resolvedKey} />
        </div>
      </div>
    </ErrorBoundary>
  )
}
