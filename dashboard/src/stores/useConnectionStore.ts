// Zustand store for WebSocket connection state
import { create } from 'zustand'
import type { ConnectionState, HelloPayload } from '@/ws/types'

interface ConnectionStore {
  state: ConnectionState
  connId: string | null
  features: string[]
  // Actions
  setConnected: (meta: HelloPayload) => void
  setState: (state: ConnectionState) => void
  reset: () => void
}

export const useConnectionStore = create<ConnectionStore>((set) => ({
  state: 'disconnected',
  connId: null,
  features: [],

  setConnected: (meta) =>
    set({
      state: 'connected',
      connId: meta.connId,
      features: meta.features ?? [],
    }),

  setState: (state) =>
    set((prev) => ({
      ...prev,
      state,
      // Clear meta when disconnected
      ...(state === 'disconnected' || state === 'failed'
        ? { connId: null, features: [] }
        : {}),
    })),

  reset: () =>
    set({ state: 'disconnected', connId: null, features: [] }),
}))
