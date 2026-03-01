// Singleton WebSocket client for NanoBot gateway
import { WS_URL, PROTOCOL_VERSION, CLIENT_INFO, RECONNECT } from '@/lib/constants'
import type {
  WireFrame,
  RequestFrame,
  ResponseFrame,
  EventFrame,
  ConnectionState,
  HelloPayload,
  ConnectParams,
  RpcErrorInfo,
} from './types'
import { RpcError } from './types'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const RPC_TIMEOUT_MS = 30_000
const DEVICE_ID_KEY = 'nanobot_device_id'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function generateId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function getOrCreateDeviceId(): string {
  let id = localStorage.getItem(DEVICE_ID_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(DEVICE_ID_KEY, id)
  }
  return id
}

function calcReconnectDelay(attempt: number): number {
  const base =
    RECONNECT.baseDelay * Math.pow(RECONNECT.multiplier, attempt)
  const capped = Math.min(base, RECONNECT.maxDelay)
  const jitter = capped * RECONNECT.jitter * (Math.random() * 2 - 1)
  return Math.round(capped + jitter)
}

// ---------------------------------------------------------------------------
// Pending RPC map entry
// ---------------------------------------------------------------------------

interface PendingRpc {
  resolve: (payload: unknown) => void
  reject: (err: RpcError) => void
  timer: ReturnType<typeof setTimeout>
}

// ---------------------------------------------------------------------------
// NanoBotWSClient
// ---------------------------------------------------------------------------

type StateChangeHandler = (state: ConnectionState, meta?: HelloPayload) => void
type EventHandler = (payload: unknown) => void

class NanoBotWSClient {
  private ws: WebSocket | null = null
  private state: ConnectionState = 'disconnected'
  private pending = new Map<string, PendingRpc>()
  private eventHandlers = new Map<string, Set<EventHandler>>()
  private stateHandlers = new Set<StateChangeHandler>()

  private reconnectAttempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private shouldReconnect = false
  private authToken = ''
  private connectReqId: string | null = null

  // Public meta from hello-ok
  connId: string | null = null
  features: string[] = []

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  setAuthToken(token: string): void {
    this.authToken = token
  }

  connect(token?: string): void {
    if (token !== undefined) this.authToken = token
    this.shouldReconnect = true
    this.reconnectAttempt = 0
    this._openSocket()
  }

  disconnect(): void {
    this.shouldReconnect = false
    this._clearReconnectTimer()
    this._closeSocket(1000, 'user disconnect')
    this._setState('disconnected')
  }

  onStateChange(handler: StateChangeHandler): () => void {
    this.stateHandlers.add(handler)
    return () => this.stateHandlers.delete(handler)
  }

  on(event: string, handler: EventHandler): () => void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, new Set())
    }
    this.eventHandlers.get(event)!.add(handler)
    return () => {
      this.eventHandlers.get(event)?.delete(handler)
    }
  }

  async rpc<T = unknown>(
    method: string,
    params: Record<string, unknown> = {},
    timeoutMs?: number,
  ): Promise<T> {
    if (this.state !== 'connected') {
      throw new RpcError({ code: 'NOT_CONNECTED', message: 'WebSocket not connected' })
    }

    const id = generateId()
    const frame: RequestFrame = { type: 'req', id, method, params }
    const timeout = timeoutMs ?? RPC_TIMEOUT_MS

    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new RpcError({ code: 'TIMEOUT', message: `RPC '${method}' timed out` }))
      }, timeout)

      this.pending.set(id, {
        resolve: (payload) => resolve(payload as T),
        reject,
        timer,
      })

      this._send(frame)
    })
  }

  // ---------------------------------------------------------------------------
  // Internal socket management
  // ---------------------------------------------------------------------------

  private _openSocket(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return
    }

    this._setState('connecting')

    try {
      this.ws = new WebSocket(WS_URL)
    } catch {
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      // Wait for challenge — server sends it first
      this._setState('challenging')
    }

    this.ws.onmessage = (evt) => {
      this._handleMessage(evt)
    }

    this.ws.onclose = (evt) => {
      this._handleClose(evt)
    }

    this.ws.onerror = () => {
      // onclose will fire right after — handle reconnect there
    }
  }

  private _closeSocket(code: number, reason: string): void {
    if (this.ws) {
      // Remove handlers before closing to avoid triggering reconnect
      this.ws.onopen = null
      this.ws.onmessage = null
      this.ws.onclose = null
      this.ws.onerror = null
      try { this.ws.close(code, reason) } catch { /* ignore */ }
      this.ws = null
    }
  }

  private _handleMessage(evt: MessageEvent): void {
    let frame: WireFrame
    try {
      frame = JSON.parse(evt.data as string) as WireFrame
    } catch {
      return
    }

    if (frame.type === 'event') {
      this._handleEvent(frame)
    } else if (frame.type === 'res') {
      this._handleResponse(frame)
    }
    // 'req' frames from server are not expected on the client side
  }

  private _handleEvent(frame: EventFrame): void {
    // During handshake, intercept connect.challenge
    if (frame.event === 'connect.challenge' && this.state === 'challenging') {
      this._sendConnectRequest()
      this._setState('authenticating')
      return
    }

    // Dispatch to registered handlers
    const handlers = this.eventHandlers.get(frame.event)
    if (handlers) {
      for (const handler of handlers) {
        try { handler(frame.payload) } catch { /* isolate handler errors */ }
      }
    }
  }

  private _handleResponse(frame: ResponseFrame): void {
    // Intercept connect response (hello-ok) to complete handshake
    if (frame.id === this.connectReqId && this.state === 'authenticating') {
      this.connectReqId = null
      if (frame.ok) {
        const meta = frame.payload as HelloPayload
        this.connId = meta.server?.connId ?? null
        this.features = meta.features?.methods ?? []
        this.reconnectAttempt = 0
        this._setState('connected', meta)
      } else {
        const errInfo = frame.error ?? { code: 'UNKNOWN', message: 'Unknown error' }
        console.error('[ws] connect rejected:', errInfo.code, errInfo.message)
        this._closeSocket(1000, 'auth rejected')
        this._setState('failed')
      }
      return
    }

    const pending = this.pending.get(frame.id)
    if (!pending) return

    clearTimeout(pending.timer)
    this.pending.delete(frame.id)

    if (frame.ok) {
      pending.resolve(frame.payload)
    } else {
      const errInfo = frame.error ?? { code: 'UNKNOWN', message: 'Unknown error' }
      pending.reject(new RpcError(errInfo as RpcErrorInfo))
    }
  }

  private _handleClose(evt: CloseEvent): void {
    // Reject all pending RPCs
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timer)
      pending.reject(new RpcError({ code: 'DISCONNECTED', message: 'WebSocket closed' }))
      this.pending.delete(id)
    }

    this.connId = null
    this.features = []

    // Close code 1012 = server restarted due to config change — reconnect immediately
    if (evt.code === 1012) {
      this._setState('connecting')
      this.reconnectAttempt = 0
      setTimeout(() => this._openSocket(), 500)
      return
    }

    if (this.shouldReconnect) {
      this._setState('disconnected')
      this._scheduleReconnect()
    } else {
      this._setState('disconnected')
    }
  }

  private _sendConnectRequest(): void {
    const params: ConnectParams = {
      minProtocol: PROTOCOL_VERSION,
      maxProtocol: PROTOCOL_VERSION,
      auth: { token: this.authToken },
      client: CLIENT_INFO,
      device: { id: getOrCreateDeviceId() },
    }

    const id = generateId()
    this.connectReqId = id

    const frame: RequestFrame = {
      type: 'req',
      id,
      method: 'connect',
      params: params as unknown as Record<string, unknown>,
    }

    this._send(frame)
  }

  private _send(frame: WireFrame): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(frame))
    }
  }

  // ---------------------------------------------------------------------------
  // Reconnect logic
  // ---------------------------------------------------------------------------

  private _scheduleReconnect(): void {
    this._clearReconnectTimer()
    const delay = calcReconnectDelay(this.reconnectAttempt)
    this.reconnectAttempt++
    this.reconnectTimer = setTimeout(() => {
      this._openSocket()
    }, delay)
  }

  private _clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  getState(): ConnectionState {
    return this.state
  }

  private _setState(state: ConnectionState, meta?: HelloPayload): void {
    this.state = state
    for (const handler of this.stateHandlers) {
      try { handler(state, meta) } catch { /* isolate */ }
    }
  }
}

// ---------------------------------------------------------------------------
// Module-level singleton
// ---------------------------------------------------------------------------

export const nanobotWS = new NanoBotWSClient()
