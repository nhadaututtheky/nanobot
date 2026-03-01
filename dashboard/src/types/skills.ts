export interface SkillInfo {
  key: string
  name: string
  source: 'workspace' | 'builtin'
  description?: string
  emoji?: string
  always?: boolean
  hasRequirements?: boolean
  available?: boolean
  installed?: boolean
  config?: Record<string, unknown>
}

export interface MarketplaceSkill {
  slug: string
  name: string
  description: string
  downloads?: number
  version?: string
  author?: string
}

export interface SubAgentRoleConfig {
  model: string
  maxIterations: number
  temperature: number
  maxTokens: number
  tools: string[]
  // Identity
  displayName: string
  description: string
  persona: string
  icon: string
  strengths: string[]
  builtin: boolean
  // Presets
  thinkingStyle: string
  persistence: string
  responseLength: string
}

export interface SubAgentConfig {
  enabled: boolean
  defaultMaxIterations: number
  defaultTemperature: number
  defaultMaxTokens: number
  roles: Record<string, SubAgentRoleConfig>
}

export interface SubAgentTask {
  id: string
  running?: boolean
  label?: string
  role?: string
  status?: string
  completedAt?: string
}

export interface SubAgentTasksInfo {
  running: SubAgentTask[]
  completed: SubAgentTask[]
  runningCount: number
}

export interface MCPServerConfig {
  command: string
  args: string[]
  env: Record<string, string>
  url: string
  headers: Record<string, string>
  toolTimeout: number
}
