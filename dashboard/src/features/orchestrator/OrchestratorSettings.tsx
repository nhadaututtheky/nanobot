import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Bot, Send, Eye, EyeOff, ChevronDown, ChevronRight } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { rpc } from '@/ws/rpc'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface OrchestratorConfig {
  telegramGroupId: string
  telegramResultChannel: string
}

interface RoleEntry {
  roleId: string
  displayName: string
  icon: string
  telegramBotToken: string
}

interface ConfigData {
  raw: string
  hash: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseConfig(raw: string): Record<string, unknown> {
  try {
    return JSON.parse(raw) as Record<string, unknown>
  } catch {
    return {}
  }
}

function getOrchestratorConfig(cfg: Record<string, unknown>): OrchestratorConfig {
  const agents = (cfg.agents ?? {}) as Record<string, unknown>
  const orch = (agents.orchestrator ?? {}) as Record<string, unknown>
  return {
    telegramGroupId: (orch.telegramGroupId ?? orch.telegram_group_id ?? '') as string,
    telegramResultChannel: (orch.telegramResultChannel ?? orch.telegram_result_channel ?? '') as string,
  }
}

function getRoleEntries(cfg: Record<string, unknown>): RoleEntry[] {
  const agents = (cfg.agents ?? {}) as Record<string, unknown>
  const subagent = (agents.subagent ?? {}) as Record<string, unknown>
  const roles = (subagent.roles ?? {}) as Record<string, Record<string, unknown>>

  const builtins: Record<string, { displayName: string; icon: string }> = {
    general: { displayName: 'General', icon: '🤖' },
    researcher: { displayName: 'Researcher', icon: '🔍' },
    coder: { displayName: 'Code Writer', icon: '💻' },
    reviewer: { displayName: 'Reviewer', icon: '📋' },
  }

  const entries: RoleEntry[] = []

  // Builtin roles first
  for (const [id, defaults] of Object.entries(builtins)) {
    const userRole = roles[id] ?? {}
    entries.push({
      roleId: id,
      displayName: (userRole.displayName as string) || (userRole.display_name as string) || defaults.displayName,
      icon: (userRole.icon as string) || defaults.icon,
      telegramBotToken: (userRole.telegramBotToken as string) || (userRole.telegram_bot_token as string) || '',
    })
  }

  // Custom roles
  for (const [id, role] of Object.entries(roles)) {
    if (id in builtins) continue
    entries.push({
      roleId: id,
      displayName: (role.displayName as string) || (role.display_name as string) || id,
      icon: (role.icon as string) || '🤖',
      telegramBotToken: (role.telegramBotToken as string) || (role.telegram_bot_token as string) || '',
    })
  }

  return entries
}

// ---------------------------------------------------------------------------
// Token input with show/hide
// ---------------------------------------------------------------------------

function TokenInput({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  const [visible, setVisible] = useState(false)

  return (
    <div className="relative">
      <Input
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="new-password"
        className="pr-10 font-mono text-xs"
      />
      <button
        type="button"
        onClick={() => setVisible(!visible)}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
        aria-label={visible ? 'Hide token' : 'Show token'}
      >
        {visible ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Role bot token row
// ---------------------------------------------------------------------------

function RoleBotRow({
  role,
  onChange,
}: {
  role: RoleEntry
  onChange: (token: string) => void
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border p-3">
      <span className="text-lg" aria-hidden="true">{role.icon}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{role.displayName}</span>
          <Badge variant="outline" className="text-[9px] px-1 py-0">{role.roleId}</Badge>
          {role.telegramBotToken && (
            <Badge variant="default" className="text-[9px] px-1 py-0 bg-primary/20 text-primary">
              bot assigned
            </Badge>
          )}
        </div>
        <div className="mt-1.5">
          <TokenInput
            value={role.telegramBotToken}
            onChange={onChange}
            placeholder="Bot token (empty = use main bot)"
          />
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function OrchestratorSettings() {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [groupId, setGroupId] = useState('')
  const [resultChannel, setResultChannel] = useState('')
  const [roles, setRoles] = useState<RoleEntry[]>([])
  const [dirty, setDirty] = useState(false)

  const { data: configData } = useQuery({
    queryKey: ['config'],
    queryFn: () => rpc.config.get(),
    select: (d) => d as ConfigData,
  })

  // Sync from server data (skip if user has unsaved edits)
  useEffect(() => {
    if (!configData?.raw || dirty) return
    const cfg = parseConfig(configData.raw)
    const orch = getOrchestratorConfig(cfg)
    setGroupId(orch.telegramGroupId)
    setResultChannel(orch.telegramResultChannel)
    setRoles(getRoleEntries(cfg))
  }, [configData?.raw]) // eslint-disable-line react-hooks/exhaustive-deps

  const saveMut = useMutation({
    mutationFn: async () => {
      // Re-fetch latest to get fresh hash
      const latest = (await rpc.config.get()) as ConfigData
      const cfg = parseConfig(latest.raw)
      const agents = (cfg.agents ?? {}) as Record<string, unknown>
      const orch = (agents.orchestrator ?? {}) as Record<string, unknown>
      const subagent = (agents.subagent ?? {}) as Record<string, unknown>
      const existingRoles = (subagent.roles ?? {}) as Record<string, Record<string, unknown>>

      // Patch orchestrator telegram fields
      const updatedOrch = {
        ...orch,
        telegramGroupId: groupId,
        telegramResultChannel: resultChannel,
      }

      // Patch role bot tokens
      const updatedRoles = { ...existingRoles }
      for (const role of roles) {
        updatedRoles[role.roleId] = {
          ...(updatedRoles[role.roleId] ?? {}),
          telegramBotToken: role.telegramBotToken,
        }
      }

      const updatedCfg = {
        ...cfg,
        agents: {
          ...agents,
          orchestrator: updatedOrch,
          subagent: {
            ...subagent,
            roles: updatedRoles,
          },
        },
      }

      await rpc.config.set({
        raw: JSON.stringify(updatedCfg, null, 2),
        baseHash: latest.hash,
      })
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['config'] })
      setDirty(false)
      toast.success('Telegram settings saved')
    },
    onError: (err) => {
      toast.error(`Save failed: ${err.message}`)
    },
  })

  const updateRole = (roleId: string, token: string) => {
    setRoles((prev) =>
      prev.map((r) => (r.roleId === roleId ? { ...r, telegramBotToken: token } : r)),
    )
    setDirty(true)
  }

  return (
    <div className="rounded-xl border border-border bg-card">
      {/* Header (clickable to expand) */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 p-4 text-left cursor-pointer hover:bg-accent/5 transition-colors rounded-xl"
      >
        <Settings className="h-5 w-5 text-muted-foreground" />
        <div className="flex-1">
          <h3 className="text-sm font-medium">Telegram Integration</h3>
          <p className="text-xs text-muted-foreground">
            Multi-bot updates for orchestrator tasks
          </p>
        </div>
        {groupId && (
          <Badge variant="outline" className="text-[10px]">
            <Send className="mr-1 h-3 w-3" />
            active
          </Badge>
        )}
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {/* Content */}
      {expanded && (
        <div className="border-t border-border p-4 space-y-4">
          {/* Group / Channel */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="orch-group-id" className="text-xs font-medium text-muted-foreground mb-1 block">
                Telegram Group ID
              </label>
              <Input
                id="orch-group-id"
                value={groupId}
                onChange={(e) => { setGroupId(e.target.value); setDirty(true) }}
                placeholder="-1001234567890"
                className="font-mono text-xs"
              />
              <p className="mt-1 text-[10px] text-muted-foreground">
                Group where sub-agents post progress updates
              </p>
            </div>
            <div>
              <label htmlFor="orch-result-channel" className="text-xs font-medium text-muted-foreground mb-1 block">
                Result Channel ID
              </label>
              <Input
                id="orch-result-channel"
                value={resultChannel}
                onChange={(e) => { setResultChannel(e.target.value); setDirty(true) }}
                placeholder="-1001234567890 (optional)"
                className="font-mono text-xs"
              />
              <p className="mt-1 text-[10px] text-muted-foreground">
                Channel for final summaries (empty = same as group)
              </p>
            </div>
          </div>

          {/* Role bot tokens */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Bot className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">
                Per-Role Bot Tokens
              </span>
            </div>
            <p className="text-[10px] text-muted-foreground mb-3">
              Assign a unique Telegram bot to each role. Each bot posts with its own identity in the group.
              Leave empty to use the main Telegram bot.
            </p>
            <div className="space-y-2">
              {roles.map((role) => (
                <RoleBotRow
                  key={role.roleId}
                  role={role}
                  onChange={(token) => updateRole(role.roleId, token)}
                />
              ))}
            </div>
          </div>

          {/* Save */}
          <div className={cn(
            'flex justify-end pt-2',
            !dirty && 'opacity-50 pointer-events-none',
          )}>
            <Button
              size="sm"
              onClick={() => saveMut.mutate()}
              disabled={saveMut.isPending || !dirty}
            >
              {saveMut.isPending ? 'Saving…' : 'Save Telegram Settings'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
