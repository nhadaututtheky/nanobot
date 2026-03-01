import { useState, useCallback, useRef, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { gatewayApi } from '@/api/gateway'
import { GATEWAY_POLL_INTERVAL_MS, GATEWAY_MAX_POLL_ATTEMPTS } from '@/lib/constants'
import type { GatewayProvider, OAuthFlowState } from '@/types/gateway'

type AuthUrlGetter = () => Promise<{ url: string; state: string }>

const AUTH_URL_GETTERS: Partial<Record<GatewayProvider, AuthUrlGetter>> = {
  anthropic: () => gatewayApi.getAnthropicAuthUrl(),
  codex: () => gatewayApi.getCodexAuthUrl(),
  gemini: () => gatewayApi.getGeminiAuthUrl(),
  iflow: () => gatewayApi.getIFlowAuthUrl(),
  qwen: () => gatewayApi.getQwenAuthUrl(),
}

// Providers that support OAuth login via gateway management API
export const OAUTH_SUPPORTED: GatewayProvider[] = ['anthropic', 'codex', 'gemini', 'iflow', 'qwen']

export function useGatewayAuth() {
  const queryClient = useQueryClient()
  const [flowState, setFlowState] = useState<OAuthFlowState>({ phase: 'idle' })
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const authWindowRef = useRef<Window | null>(null)

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => stopPolling()
  }, [stopPolling])

  const startOAuth = useCallback(async (provider: GatewayProvider) => {
    const getter = AUTH_URL_GETTERS[provider]
    if (!getter) {
      toast.error(`OAuth not available for ${provider}`)
      return
    }

    // Open blank window SYNCHRONOUSLY to avoid popup blocker
    const authWindow = window.open('about:blank', '_blank', 'noopener')
    authWindowRef.current = authWindow

    setFlowState({ phase: 'opening', provider })

    try {
      const { url, state } = await getter()

      // Navigate the already-opened window to auth URL
      if (authWindow && !authWindow.closed) {
        authWindow.location.href = url
      } else {
        // Window was blocked — fall back to direct open
        window.open(url, '_blank', 'noopener,noreferrer')
      }

      let attempts = 0
      setFlowState({ phase: 'polling', provider, state, attempts: 0, authUrl: url })

      pollTimerRef.current = setInterval(async () => {
        attempts++

        if (attempts > GATEWAY_MAX_POLL_ATTEMPTS) {
          stopPolling()
          setFlowState({ phase: 'error', provider, message: 'OAuth timed out (3 min). Please try again.' })
          return
        }

        setFlowState({ phase: 'polling', provider, state, attempts, authUrl: url })

        try {
          const status = await gatewayApi.getAuthStatus(state)
          if (status.completed) {
            stopPolling()
            if (status.success !== false) {
              setFlowState({ phase: 'success', provider })
              toast.success(`${provider} connected successfully`)
              void queryClient.invalidateQueries({ queryKey: ['gateway', 'auth-files'] })
              setTimeout(() => setFlowState({ phase: 'idle' }), 3000)
            } else {
              setFlowState({ phase: 'error', provider, message: status.error ?? 'OAuth failed' })
            }
          }
        } catch {
          // Network error during poll — keep trying
        }
      }, GATEWAY_POLL_INTERVAL_MS)

    } catch (err) {
      // Close the blank window if auth URL fetch failed
      if (authWindow && !authWindow.closed) authWindow.close()
      const message = err instanceof Error ? err.message : 'Failed to start OAuth'
      setFlowState({ phase: 'error', provider, message })
      toast.error(`OAuth failed for ${provider}`, { description: message })
    }
  }, [queryClient, stopPolling])

  const cancelOAuth = useCallback(() => {
    stopPolling()
    setFlowState({ phase: 'idle' })
  }, [stopPolling])

  const reopenAuthUrl = useCallback(() => {
    if (flowState.phase === 'polling') {
      window.open(flowState.authUrl, '_blank', 'noopener,noreferrer')
    }
  }, [flowState])

  return { flowState, startOAuth, cancelOAuth, reopenAuthUrl }
}
