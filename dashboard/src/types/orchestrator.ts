// Orchestrator types — mirrors nanobot/orchestrator/models.py

export type TaskCapability =
  | 'reasoning'
  | 'coding'
  | 'research'
  | 'creative'
  | 'data_analysis'
  | 'translation'
  | 'summarization'
  | 'general'

export type TaskStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'skipped'

export type GraphStatus =
  | 'draft'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface TaskNode {
  id: string
  label: string
  description: string
  capability: TaskCapability
  workerRole: string
  status: TaskStatus
  assignedModel: string
  result: string
  progress: number
  inputContext: string
  outputSummary: string
  error: string
  startedAt: string
  completedAt: string
}

export interface TaskEdge {
  fromId: string
  toId: string
}

export interface TaskGraph {
  id: string
  goal: string
  nodes: TaskNode[]
  edges: TaskEdge[]
  status: GraphStatus
  originChannel: string
  originChatId: string
  createdAt: string
  startedAt: string
  completedAt: string
  progress: number
}

export interface GraphSummary {
  id: string
  goal: string
  status: GraphStatus
  nodeCount: number
  progress: number
  createdAt: string
  completedAt: string
}

export interface ModelInfo {
  model: string
  provider: string
  capabilities: string[]
  tier: 'high' | 'mid' | 'low'
  costInput: number
  costOutput: number
  contextWindow: number
}

export interface OrchestratorEventPayload {
  type:
    | 'graph_started'
    | 'node_started'
    | 'node_progress'
    | 'node_done'
    | 'graph_done'
    | 'graph_cancelled'
  graphId: string
  status: GraphStatus
  progress: number
  node?: TaskNode
}
