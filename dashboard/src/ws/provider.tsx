// React context and hooks for the NanoBot WebSocket client
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactNode,
} from 'react'
import { nanobotWS } from './client'
import { useConnectionStore } from '@/stores/useConnectionStore'
import type { ConnectionState, HelloPayload } from './types'

// ---------------------------------------------------------------------------
// Context value shape
// ---------------------------------------------------------------------------

interface WSContextValue {
  state: ConnectionState
  connId: string | null
  features: string[]
  connect: (token?: string) => void
  disconnect: () => void
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const WSContext = createContext<WSContextValue | null>(null)

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface WebSocketProviderProps {
  children: ReactNode
  token?: string
}

export function WebSocketProvider({ children, token = '' }: WebSocketProviderProps) {
  const setConnected = useConnectionStore((s) => s.setConnected)
  const setStoreState = useConnectionStore((s) => s.setState)
  const state = useConnectionStore((s) => s.state)
  const connId = useConnectionStore((s) => s.connId)
  const features = useConnectionStore((s) => s.features)

  // Keep token ref stable so the effect closure doesn't need to re-run
  const tokenRef = useRef(token)
  tokenRef.current = token

  useEffect(() => {
    // Sync WS state changes into Zustand store
    const unsubState = nanobotWS.onStateChange((wsState: ConnectionState, meta?: HelloPayload) => {
      if (wsState === 'connected' && meta) {
        setConnected(meta)
      } else {
        setStoreState(wsState)
      }
    })

    // Connect with current token
    nanobotWS.connect(tokenRef.current)

    return () => {
      unsubState()
      nanobotWS.disconnect()
    }
    // Empty deps: run once on mount; token changes are handled via ref
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const value: WSContextValue = {
    state,
    connId,
    features,
    connect: (t?: string) => nanobotWS.connect(t),
    disconnect: () => nanobotWS.disconnect(),
  }

  return <WSContext.Provider value={value}>{children}</WSContext.Provider>
}

// ---------------------------------------------------------------------------
// useWS hook
// ---------------------------------------------------------------------------

export function useWS(): WSContextValue {
  const ctx = useContext(WSContext)
  if (!ctx) {
    throw new Error('useWS must be used inside <WebSocketProvider>')
  }
  return ctx
}

// ---------------------------------------------------------------------------
// useEvent hook — subscribes to a broadcast event, auto-unsubscribes on unmount
// ---------------------------------------------------------------------------

export function useEvent(
  eventName: string,
  handler: (payload: unknown) => void,
): void {
  // Keep handler ref to avoid stale closures when handler changes each render
  const handlerRef = useRef(handler)
  handlerRef.current = handler

  useEffect(() => {
    const unsub = nanobotWS.on(eventName, (payload: unknown) => {
      handlerRef.current(payload)
    })
    return unsub
  }, [eventName])
}
