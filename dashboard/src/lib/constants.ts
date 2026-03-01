export const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:18790'
export const PROTOCOL_VERSION = 3

export const CLIENT_INFO = {
  name: 'NanoBot Dashboard',
  version: '0.1.0',
} as const

export const RECONNECT = {
  baseDelay: 3000,
  maxDelay: 30000,
  multiplier: 1.5,
  jitter: 0.3,
} as const

export const CHANNEL_ICONS: Record<string, string> = {
  telegram: 'MessageCircle',
  discord: 'Gamepad2',
  whatsapp: 'Phone',
  slack: 'Hash',
  email: 'Mail',
  feishu: 'Bird',
  dingtalk: 'Bell',
  qq: 'MessageSquare',
  matrix: 'Globe',
} as const

export const NAV_ITEMS = [
  { path: '/', label: 'Overview', icon: 'LayoutDashboard' },
  { path: '/chat', label: 'Chat', icon: 'MessageSquare' },
  { path: '/config', label: 'Config', icon: 'Settings' },
  { path: '/cron', label: 'Cron', icon: 'Clock' },
  { path: '/analytics', label: 'Analytics', icon: 'BarChart3' },
] as const

// AI Gateway (CLIProxyAPI-compatible management API)
export const GATEWAY_MGMT_URL_KEY = 'gateway_mgmt_url'
export const GATEWAY_DEFAULT_MGMT = '/ai-gateway'
export const GATEWAY_TIMEOUT_MS = 8000
export const GATEWAY_POLL_INTERVAL_MS = 2000
export const GATEWAY_MAX_POLL_ATTEMPTS = 90 // 3 min at 2s intervals
