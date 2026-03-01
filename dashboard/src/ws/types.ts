// WebSocket protocol types for NanoBot gateway (protocol version 3)

// ---------------------------------------------------------------------------
// Wire frames
// ---------------------------------------------------------------------------

export interface RequestFrame {
  type: 'req'
  id: string
  method: string
  params: Record<string, unknown>
}

export interface ResponseFrame {
  type: 'res'
  id: string
  ok: boolean
  payload?: unknown
  error?: RpcErrorInfo
}

export interface EventFrame {
  type: 'event'
  event: string
  payload?: unknown
  seq?: number
  stateVersion?: Record<string, number>
}

export type WireFrame = RequestFrame | ResponseFrame | EventFrame

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

export interface RpcErrorInfo {
  code: string
  message: string
  details?: unknown
}

export class RpcError extends Error {
  readonly code: string
  readonly details: unknown

  constructor(info: RpcErrorInfo) {
    super(info.message)
    this.name = 'RpcError'
    this.code = info.code
    this.details = info.details
  }
}

// ---------------------------------------------------------------------------
// Connection state
// ---------------------------------------------------------------------------

export type ConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'challenging'
  | 'authenticating'
  | 'connected'
  | 'failed'

// ---------------------------------------------------------------------------
// Broadcast event names
// ---------------------------------------------------------------------------

export type BroadcastEvent =
  | 'chat'
  | 'cron'
  | 'presence'
  | 'agent'
  | 'orchestrator'
  | 'device.pair.requested'
  | 'device.pair.resolved'
  | 'exec.approval.requested'
  | 'exec.approval.resolved'

// ---------------------------------------------------------------------------
// Handshake payloads
// ---------------------------------------------------------------------------

export interface ChallengePayload {
  challenge: string
  serverVersion: string
}

export interface HelloPayload {
  type: 'hello-ok'
  protocol: number
  server: {
    version: string
    connId: string
  }
  features: {
    methods: string[]
    events: string[]
  }
  auth: {
    role: string
    scopes: string[]
    issuedAtMs: number
  }
  policy: {
    tickIntervalMs: number
  }
  // Derived helpers set by client
  connId?: string
  serverVersion?: string
}

// ---------------------------------------------------------------------------
// Broadcast event payloads
// ---------------------------------------------------------------------------

export interface ChatEventPayload {
  sessionKey: string
  channelId: string
  role: 'user' | 'assistant' | 'context' | 'tool'
  content: string
  timestamp: string
  msgId?: string
}

export interface CronEventPayload {
  jobId: string
  event: 'started' | 'finished' | 'failed'
  timestamp: string
  duration?: number
  error?: string
}

export interface PresenceEventPayload {
  connId: string
  event: 'joined' | 'left'
  clientName?: string
}

export interface AgentEventPayload {
  sessionKey: string
  event: 'thinking' | 'tool_call' | 'tool_result' | 'done'
  tool?: string
  content?: string
}

export interface DevicePairRequestedPayload {
  deviceId: string
  requestId: string
  clientName: string
  timestamp: string
}

export interface DevicePairResolvedPayload {
  requestId: string
  approved: boolean
}

export interface ExecApprovalRequestedPayload {
  approvalId: string
  sessionKey: string
  command: string
  args: string[]
  timestamp: string
}

export interface ExecApprovalResolvedPayload {
  approvalId: string
  approved: boolean
}

// ---------------------------------------------------------------------------
// Connect request params
// ---------------------------------------------------------------------------

export interface ConnectParams {
  minProtocol: number
  maxProtocol: number
  auth: { token: string }
  client: { name: string; version: string }
  device: { id: string }
}
