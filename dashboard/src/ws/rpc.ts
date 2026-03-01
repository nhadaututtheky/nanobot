// Typed RPC wrappers for all 53 NanoBot gateway endpoints
import { nanobotWS } from './client'

// ---------------------------------------------------------------------------
// Helper — forwards to singleton client
// ---------------------------------------------------------------------------

function call<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  return nanobotWS.rpc<T>(method, params)
}

// ---------------------------------------------------------------------------
// RPC namespace object
// ---------------------------------------------------------------------------

export const rpc = {
  // -------------------------------------------------------------------------
  // System
  // -------------------------------------------------------------------------

  system: {
    status: () =>
      call('status'),

    health: () =>
      call('health'),

    modelsList: () =>
      call('models.list'),

    lastHeartbeat: () =>
      call('last-heartbeat'),

    systemPresence: () =>
      call('system-presence'),

    logsTail: (params: { lines?: number; level?: string } = {}) =>
      call('logs.tail', params as Record<string, unknown>),

    updateRun: () =>
      call('update.run'),

    usageCost: (params: { period?: string } = {}) =>
      call('usage.cost', params as Record<string, unknown>),
  },

  // -------------------------------------------------------------------------
  // Chat
  // -------------------------------------------------------------------------

  chat: {
    send: (params: {
      sessionKey: string
      content: string
      channelId?: string
    }) => call('chat.send', params as Record<string, unknown>),

    history: (params: {
      sessionKey: string
      limit?: number
      before?: string
    }) => call('chat.history', params as Record<string, unknown>),

    abort: (params: { sessionKey: string }) =>
      call('chat.abort', params as Record<string, unknown>),
  },

  // -------------------------------------------------------------------------
  // Sessions
  // -------------------------------------------------------------------------

  sessions: {
    list: (params: { channelId?: string; limit?: number } = {}) =>
      call('sessions.list', params as Record<string, unknown>),

    patch: (params: { sessionKey: string; updates: Record<string, unknown> }) =>
      call('sessions.patch', params as Record<string, unknown>),

    delete: (params: { sessionKey: string }) =>
      call('sessions.delete', params as Record<string, unknown>),

    usage: (params: { sessionKey: string }) =>
      call('sessions.usage', params as Record<string, unknown>),

    usageTimeseries: (params: {
      sessionKey: string
      period?: string
      granularity?: string
    }) => call('sessions.usage.timeseries', params as Record<string, unknown>),

    usageLogs: (params: { sessionKey: string; limit?: number }) =>
      call('sessions.usage.logs', params as Record<string, unknown>),
  },

  // -------------------------------------------------------------------------
  // Config
  // -------------------------------------------------------------------------

  config: {
    get: () =>
      call('config.get'),

    schema: () =>
      call('config.schema'),

    set: (params: { patch: Record<string, unknown> }) =>
      call('config.set', params as Record<string, unknown>),

    apply: () =>
      call('config.apply'),
  },

  // -------------------------------------------------------------------------
  // Cron
  // -------------------------------------------------------------------------

  cron: {
    status: () =>
      call('cron.status'),

    list: () =>
      call('cron.list'),

    add: (params: {
      expression: string
      task: string
      sessionKey?: string
      enabled?: boolean
    }) => call('cron.add', params as Record<string, unknown>),

    update: (params: {
      jobId: string
      expression?: string
      task?: string
      enabled?: boolean
    }) => call('cron.update', params as Record<string, unknown>),

    run: (params: { jobId: string }) =>
      call('cron.run', params as Record<string, unknown>),

    remove: (params: { jobId: string }) =>
      call('cron.remove', params as Record<string, unknown>),

    runs: (params: { jobId?: string; limit?: number } = {}) =>
      call('cron.runs', params as Record<string, unknown>),
  },

  // -------------------------------------------------------------------------
  // Channels
  // -------------------------------------------------------------------------

  channels: {
    status: () =>
      call('channels.status'),

    logout: (params: { channelId: string }) =>
      call('channels.logout', params as Record<string, unknown>),

    webLoginStart: (params: { channelId: string }) =>
      call('web.login.start', params as Record<string, unknown>),

    webLoginWait: (params: { channelId: string; requestId: string }) =>
      call('web.login.wait', params as Record<string, unknown>),
  },

  // -------------------------------------------------------------------------
  // Agents
  // -------------------------------------------------------------------------

  agents: {
    list: () =>
      call('agents.list'),

    identityGet: (params: { agentId: string }) =>
      call('agent.identity.get', params as Record<string, unknown>),

    filesList: (params: { agentId: string }) =>
      call('agents.files.list', params as Record<string, unknown>),

    filesGet: (params: { agentId: string; path: string }) =>
      call('agents.files.get', params as Record<string, unknown>),

    filesSet: (params: { agentId: string; path: string; content: string }) =>
      call('agents.files.set', params as Record<string, unknown>),

    toolsCatalog: () =>
      call('tools.catalog'),
  },

  // -------------------------------------------------------------------------
  // Skills
  // -------------------------------------------------------------------------

  skills: {
    status: () =>
      call('skills.status'),

    update: (params: { skillId: string; patch: Record<string, unknown> }) =>
      call('skills.update', params as Record<string, unknown>),

    install: (params: { source: string; name?: string }) =>
      call('skills.install', params as Record<string, unknown>),
  },

  // -------------------------------------------------------------------------
  // Devices
  // -------------------------------------------------------------------------

  devices: {
    pairList: () =>
      call('device.pair.list'),

    pairApprove: (params: { requestId: string }) =>
      call('device.pair.approve', params as Record<string, unknown>),

    pairReject: (params: { requestId: string }) =>
      call('device.pair.reject', params as Record<string, unknown>),

    tokenRotate: (params: { deviceId: string }) =>
      call('device.token.rotate', params as Record<string, unknown>),

    tokenRevoke: (params: { deviceId: string }) =>
      call('device.token.revoke', params as Record<string, unknown>),
  },

  // -------------------------------------------------------------------------
  // Exec Approvals
  // -------------------------------------------------------------------------

  execApprovals: {
    get: () =>
      call('exec.approvals.get'),

    set: (params: { rules: Record<string, unknown> }) =>
      call('exec.approvals.set', params as Record<string, unknown>),

    nodeGet: (params: { nodeId: string }) =>
      call('exec.approvals.node.get', params as Record<string, unknown>),

    nodeSet: (params: { nodeId: string; rules: Record<string, unknown> }) =>
      call('exec.approvals.node.set', params as Record<string, unknown>),

    resolve: (params: { approvalId: string; approved: boolean; reason?: string }) =>
      call('exec.approval.resolve', params as Record<string, unknown>),
  },

  // -------------------------------------------------------------------------
  // Nodes
  // -------------------------------------------------------------------------

  nodes: {
    list: () =>
      call('node.list'),
  },

  // -------------------------------------------------------------------------
  // AI Gateway (CLIProxyAPI service management)
  // -------------------------------------------------------------------------

  aiGateway: {
    status: () =>
      call<{
        running: boolean
        pid: number | null
        binaryFound: boolean
        binaryPath: string | null
        managementUrl: string
        proxyUrl: string
        enabled: boolean
      }>('ai-gateway.status'),

    start: () =>
      call<{ ok: boolean; pid: number; alreadyRunning: boolean }>('ai-gateway.start'),

    stop: () =>
      call<{ ok: boolean; wasRunning: boolean; pid?: number }>('ai-gateway.stop'),
  },
} as const
