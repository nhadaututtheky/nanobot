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
      {/* Full-height split layout — h-[calc] minus TopBar(3rem)+padding(2rem), overflow-hidden to constrain children */}
      <div className="flex h-[calc(100vh-5rem)] overflow-hidden rounded-xl border border-border">
        {/* Session list — fixed 280px on desktop, min-h-0 lets flex child shrink below content */}
        <div className="hidden w-[280px] shrink-0 md:flex md:flex-col min-h-0 overflow-hidden">
          <SessionList />
        </div>

        {/* Mobile: session list above, panel below */}
        <div className="flex flex-1 flex-col md:hidden min-h-0 overflow-hidden">
          {resolvedKey ? (
            <ChatPanel sessionKey={resolvedKey} />
          ) : (
            <SessionList />
          )}
        </div>

        {/* Desktop: chat panel — min-h-0 lets flex child shrink so ScrollArea works */}
        <div className="hidden flex-1 flex-col md:flex min-h-0 overflow-hidden">
          <ChatPanel sessionKey={resolvedKey} />
        </div>
      </div>
    </ErrorBoundary>
  )
}
