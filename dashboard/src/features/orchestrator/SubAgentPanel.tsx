import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { rpc } from '@/ws/rpc'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { SubAgentConfig, SubAgentRoleConfig, SubAgentTasksInfo } from '@/types/skills'
import { SubAgentRoleCard } from './SubAgentRoleCard'
import { SubAgentCreateDialog } from './SubAgentCreateDialog'
import {
  THINKING_STYLE_OPTIONS,
  PERSISTENCE_OPTIONS,
  RESPONSE_LENGTH_OPTIONS,
} from './SubAgentPresets'

interface ConfigData {
  raw: string
  hash: string
}

const DEFAULT_ROLE: SubAgentRoleConfig = {
  model: '',
  maxIterations: 0,
  temperature: 0,
  maxTokens: 0,
  tools: [],
  displayName: '',
  description: '',
  persona: '',
  icon: '🤖',
  strengths: [],
  builtin: false,
  thinkingStyle: 'balanced',
  persistence: 'normal',
  responseLength: 'normal',
}

export function SubAgentPanel() {
  const queryClient = useQueryClient()
  const { data: configData } = useQuery({
    queryKey: ['config', 'get'],
    queryFn: () => rpc.config.get() as Promise<ConfigData>,
  })

  const { data: subagentConfig, isLoading: configLoading } = useQuery({
    queryKey: ['subagent', 'config'],
    queryFn: () => rpc.agents.subagentConfigGet(),
  })

  const { data: tasks } = useQuery({
    queryKey: ['subagent', 'tasks'],
    queryFn: () => rpc.agents.subagentTasksList(),
    refetchInterval: 5_000,
  })

  const config: SubAgentConfig = subagentConfig ?? {
    enabled: true,
    defaultMaxIterations: 15,
    defaultTemperature: 0.7,
    defaultMaxTokens: 4096,
    roles: {},
  }

  const tasksInfo: SubAgentTasksInfo = tasks ?? {
    running: [],
    completed: [],
    runningCount: 0,
  }

  const roleEntries = Object.entries(config.roles).map(([id, cfg]) => ({
    id,
    config: { ...DEFAULT_ROLE, ...cfg },
  }))

  // Sort: builtin first, then custom
  roleEntries.sort((a, b) => {
    if (a.config.builtin && !b.config.builtin) return -1
    if (!a.config.builtin && b.config.builtin) return 1
    return 0
  })

  async function saveSubagentConfig(patch: Partial<SubAgentConfig>) {
    if (!configData) return
    try {
      const fullConfig = JSON.parse(configData.raw)
      const agents = fullConfig.agents ?? {}
      const current = agents.subagent ?? {}
      const updated = { ...current, ...patch }

      const updatedConfig = {
        ...fullConfig,
        agents: { ...agents, subagent: updated },
      }
      await rpc.config.set({
        raw: JSON.stringify(updatedConfig, null, 2),
        baseHash: configData.hash,
      })
      queryClient.invalidateQueries({ queryKey: ['config', 'get'] })
      queryClient.invalidateQueries({ queryKey: ['subagent', 'config'] })
      toast.success('Sub-agent config saved')
    } catch (err) {
      toast.error(`Save failed: ${err instanceof Error ? err.message : 'unknown'}`)
    }
  }

  function handleRoleUpdate(roleId: string, patch: Partial<SubAgentRoleConfig>) {
    const currentRoles = config.roles ?? {}
    const current = currentRoles[roleId] ?? {}
    const roles = {
      ...currentRoles,
      [roleId]: { ...current, ...patch },
    }
    saveSubagentConfig({ roles })
  }

  function handleRoleDelete(roleId: string) {
    const currentRoles = { ...config.roles }
    delete currentRoles[roleId]
    saveSubagentConfig({ roles: currentRoles })
  }

  function handleRoleCreate(roleId: string, roleCfg: SubAgentRoleConfig) {
    const roles = { ...config.roles, [roleId]: roleCfg }
    saveSubagentConfig({ roles })
  }

  // Detect current default presets from raw values
  const defaultThinking =
    THINKING_STYLE_OPTIONS.find((o) => o.raw === config.defaultTemperature)?.value ?? ''
  const defaultPersistence =
    PERSISTENCE_OPTIONS.find((o) => o.raw === config.defaultMaxIterations)?.value ?? ''
  const defaultResponse =
    RESPONSE_LENGTH_OPTIONS.find((o) => o.raw === config.defaultMaxTokens)?.value ?? ''

  if (configLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Defaults */}
      <Card className="space-y-4 p-4">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold">Defaults</h4>
          <div className="flex items-center gap-2">
            <Label htmlFor="subagent-enabled" className="text-xs">
              Enabled
            </Label>
            <Switch
              id="subagent-enabled"
              checked={config.enabled}
              onCheckedChange={(v) => saveSubagentConfig({ enabled: v })}
            />
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Thinking</Label>
            <Select
              value={defaultThinking}
              onValueChange={(v) => {
                const opt = THINKING_STYLE_OPTIONS.find((o) => o.value === v)
                if (opt) saveSubagentConfig({ defaultTemperature: opt.raw })
              }}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Custom" />
              </SelectTrigger>
              <SelectContent>
                {THINKING_STYLE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Persistence</Label>
            <Select
              value={defaultPersistence}
              onValueChange={(v) => {
                const opt = PERSISTENCE_OPTIONS.find((o) => o.value === v)
                if (opt) saveSubagentConfig({ defaultMaxIterations: opt.raw })
              }}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Custom" />
              </SelectTrigger>
              <SelectContent>
                {PERSISTENCE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Response</Label>
            <Select
              value={defaultResponse}
              onValueChange={(v) => {
                const opt = RESPONSE_LENGTH_OPTIONS.find((o) => o.value === v)
                if (opt) saveSubagentConfig({ defaultMaxTokens: opt.raw })
              }}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Custom" />
              </SelectTrigger>
              <SelectContent>
                {RESPONSE_LENGTH_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </Card>

      {/* Role Cards */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-sm font-semibold">Sub-Agents</h4>
          <SubAgentCreateDialog
            existingRoles={roleEntries.map((r) => r.id)}
            onCreateRole={handleRoleCreate}
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {roleEntries.map(({ id, config: roleCfg }) => (
            <SubAgentRoleCard
              key={id}
              roleId={id}
              config={roleCfg}
              onUpdate={handleRoleUpdate}
              onDelete={roleCfg.builtin ? undefined : handleRoleDelete}
            />
          ))}
        </div>
      </div>

      {/* Running Tasks */}
      <div>
        <div className="mb-3 flex items-center gap-2">
          <h4 className="text-sm font-semibold">Active Tasks</h4>
          <Badge variant="outline" className="text-[10px]">
            {tasksInfo.runningCount} running
          </Badge>
        </div>
        {tasksInfo.running.length === 0 && tasksInfo.completed.length === 0 ? (
          <p className="py-4 text-center text-xs text-muted-foreground">
            No recent sub-agent tasks.
          </p>
        ) : (
          <div className="space-y-1.5">
            {tasksInfo.running.map((t) => (
              <div
                key={t.id}
                className="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2 text-xs"
              >
                <Loader2 className="h-3 w-3 animate-spin text-primary" />
                <span className="font-mono">{t.id}</span>
                {t.label && <span className="text-muted-foreground">{t.label}</span>}
              </div>
            ))}
            {tasksInfo.completed.slice(-10).reverse().map((t) => (
              <div
                key={`${t.id}-${t.completedAt}`}
                className="flex items-center gap-2 rounded-lg bg-muted/30 px-3 py-2 text-xs"
              >
                {t.status === 'ok' ? (
                  <CheckCircle className="h-3 w-3 text-green-500" />
                ) : (
                  <XCircle className="h-3 w-3 text-destructive" />
                )}
                <span className="font-mono">{t.id}</span>
                {t.role && (
                  <Badge variant="secondary" className="text-[9px]">
                    {t.role}
                  </Badge>
                )}
                {t.label && (
                  <span className="truncate text-muted-foreground">{t.label}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
