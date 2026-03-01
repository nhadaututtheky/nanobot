import { create } from 'zustand'

interface ChatState {
  activeSessionKey: string | null
  activeRunId: string | null
  isStreaming: boolean
  streamBuffer: Map<string, string>

  setActiveSession: (key: string | null) => void
  startStreaming: (runId: string) => void
  appendDelta: (runId: string, text: string) => void
  stopStreaming: () => void
  getStreamContent: (runId: string) => string
  clearStream: (runId: string) => void
}

export const useChatStore = create<ChatState>()((set, get) => ({
  activeSessionKey: null,
  activeRunId: null,
  isStreaming: false,
  streamBuffer: new Map(),

  setActiveSession: (key) => set({ activeSessionKey: key }),

  startStreaming: (runId) =>
    set((state) => {
      const buffer = new Map(state.streamBuffer)
      buffer.set(runId, '')
      return { activeRunId: runId, isStreaming: true, streamBuffer: buffer }
    }),

  appendDelta: (runId, text) =>
    set((state) => {
      const buffer = new Map(state.streamBuffer)
      const current = buffer.get(runId) ?? ''
      buffer.set(runId, current + text)
      return { streamBuffer: buffer }
    }),

  stopStreaming: () => set({ isStreaming: false, activeRunId: null }),

  getStreamContent: (runId) => get().streamBuffer.get(runId) ?? '',

  clearStream: (runId) =>
    set((state) => {
      const buffer = new Map(state.streamBuffer)
      buffer.delete(runId)
      return { streamBuffer: buffer }
    }),
}))
