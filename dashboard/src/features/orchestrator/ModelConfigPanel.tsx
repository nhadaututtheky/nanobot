import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Cpu,
  Plus,
  Trash2,
  Pencil,
  ChevronDown,
  ChevronRight,
  Zap,
  Brain,
  Code,
  Search,
  Palette,
  BarChart3,
  Globe,
  FileText,
  Bot,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { rpc } from '@/ws/rpc'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ModelEntry {
  model: string
  provider: string
  capabilities: string[]
  tier: string
  costInput: number
  costOutput: number
  contextWindow: number
}

interface ConfigData {
  raw: string
  hash: string
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALL_CAPABILITIES = [
  'reasoning',
  'coding',
  'research',
  'creative',
  'data_analysis',
  'translation',
  'summarization',
  'general',
] as const

const CAPABILITY_ICONS: Record<string, typeof Brain> = {
  reasoning: Brain,
  coding: Code,
  research: Search,
  creative: Palette,
  data_analysis: BarChart3,
  translation: Globe,
  summarization: FileText,
  general: Bot,
}

const TIER_COLORS: Record<string, string> = {
  high: 'bg-amber-500/15 text-amber-500 border-amber-500/30',
  mid: 'bg-blue-500/15 text-blue-500 border-blue-500/30',
  low: 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30',
}

const TIER_LABELS: Record<string, string> = {
  high: 'High',
  mid: 'Mid',
  low: 'Low',
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

function getModelsFromConfig(cfg: Record<string, unknown>): ModelEntry[] {
  const agents = (cfg.agents ?? {}) as Record<string, unknown>
  const orch = (agents.orchestrator ?? {}) as Record<string, unknown>
  const models = (orch.models ?? []) as Record<string, unknown>[]

  return models.map((m) => ({
    model: (m.model ?? '') as string,
    provider: (m.provider ?? '') as string,
    capabilities: (m.capabilities ?? []) as string[],
    tier: (m.tier ?? 'mid') as string,
    costInput: (m.costInput ?? m.cost_input ?? 0) as number,
    costOutput: (m.costOutput ?? m.cost_output ?? 0) as number,
    contextWindow: (m.contextWindow ?? m.context_window ?? 128000) as number,
  }))
}

function formatCtxWindow(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}

function emptyModel(): ModelEntry {
  return {
    model: '',
    provider: '',
    capabilities: ['general'],
    tier: 'mid',
    costInput: 0,
    costOutput: 0,
    contextWindow: 128000,
  }
}

// ---------------------------------------------------------------------------
// Capability toggle chips
// ---------------------------------------------------------------------------

function CapabilityChips({
  selected,
  onChange,
}: {
  selected: string[]
  onChange: (caps: string[]) => void
}) {
  const toggle = (cap: string) => {
    if (selected.includes(cap)) {
      onChange(selected.filter((c) => c !== cap))
    } else {
      onChange([...selected, cap])
    }
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {ALL_CAPABILITIES.map((cap) => {
        const Icon = CAPABILITY_ICONS[cap] ?? Bot
        const active = selected.includes(cap)
        return (
          <button
            key={cap}
            type="button"
            onClick={() => toggle(cap)}
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors cursor-pointer',
              active
                ? 'bg-primary/15 text-primary border-primary/30'
                : 'bg-muted/50 text-muted-foreground border-transparent hover:border-border',
            )}
          >
            <Icon className="h-2.5 w-2.5" />
            {cap.replace('_', ' ')}
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Model card (read-only row)
// ---------------------------------------------------------------------------

function ModelCard({
  model,
  onEdit,
  onDelete,
}: {
  model: ModelEntry
  onEdit: () => void
  onDelete: () => void
}) {
  const modelShort = model.model.includes('/')
    ? model.model.split('/').slice(1).join('/')
    : model.model
  const isFree = model.costInput === 0 && model.costOutput === 0

  return (
    <div className="group flex items-start gap-3 rounded-lg border border-border p-3 transition-colors hover:border-primary/20">
      <Cpu className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium font-mono">{modelShort}</span>
          <Badge variant="outline" className="text-[9px] px-1 py-0">
            {model.provider}
          </Badge>
          <Badge
            variant="outline"
            className={cn('text-[9px] px-1.5 py-0 border', TIER_COLORS[model.tier])}
          >
            {TIER_LABELS[model.tier] ?? model.tier}
          </Badge>
          {isFree && (
            <Badge variant="outline" className="text-[9px] px-1 py-0 bg-emerald-500/10 text-emerald-500 border-emerald-500/30">
              free
            </Badge>
          )}
        </div>

        <div className="mt-1.5 flex items-center gap-3 text-[10px] text-muted-foreground">
          <span>ctx: {formatCtxWindow(model.contextWindow)}</span>
          {!isFree && (
            <>
              <span>in: ${model.costInput}/1K</span>
              <span>out: ${model.costOutput}/1K</span>
            </>
          )}
        </div>

        <div className="mt-1.5 flex flex-wrap gap-1">
          {model.capabilities.map((cap) => {
            const Icon = CAPABILITY_ICONS[cap] ?? Bot
            return (
              <span
                key={cap}
                className="inline-flex items-center gap-0.5 rounded-full bg-muted/50 px-1.5 py-0 text-[9px] text-muted-foreground"
              >
                <Icon className="h-2 w-2" />
                {cap.replace('_', ' ')}
              </span>
            )
          })}
        </div>
      </div>

      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          type="button"
          onClick={onEdit}
          className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent cursor-pointer"
          aria-label="Edit model"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="rounded-md p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 cursor-pointer"
          aria-label="Delete model"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Add / Edit dialog
// ---------------------------------------------------------------------------

function ModelDialog({
  open,
  onOpenChange,
  initial,
  onSave,
  title,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  initial: ModelEntry
  onSave: (model: ModelEntry) => void
  title: string
}) {
  const [form, setForm] = useState<ModelEntry>(initial)

  useEffect(() => {
    if (open) setForm(initial)
  }, [open, initial])

  const update = <K extends keyof ModelEntry>(key: K, value: ModelEntry[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const valid = form.model.trim() !== '' && form.provider.trim() !== '' && form.capabilities.length > 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            Configure model routing for orchestrator tasks.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Model ID */}
          <div>
            <label htmlFor="model-id" className="text-xs font-medium text-muted-foreground mb-1 block">
              Model ID
            </label>
            <Input
              id="model-id"
              value={form.model}
              onChange={(e) => update('model', e.target.value)}
              placeholder="dashscope/qwen3.5-plus"
              className="font-mono text-xs"
            />
            <p className="mt-1 text-[10px] text-muted-foreground">
              Format: provider/model-name (e.g. dashscope/qwen3-coder-plus)
            </p>
          </div>

          {/* Provider + Tier */}
          <div className="grid gap-3 grid-cols-2">
            <div>
              <label htmlFor="model-provider" className="text-xs font-medium text-muted-foreground mb-1 block">
                Provider
              </label>
              <Input
                id="model-provider"
                value={form.provider}
                onChange={(e) => update('provider', e.target.value)}
                placeholder="dashscope"
                className="text-xs"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Tier
              </label>
              <Select value={form.tier} onValueChange={(v) => update('tier', v)}>
                <SelectTrigger className="w-full text-xs h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="high">
                    <Zap className="mr-1 inline h-3 w-3 text-amber-500" />
                    High — reasoning, complex tasks
                  </SelectItem>
                  <SelectItem value="mid">
                    <Code className="mr-1 inline h-3 w-3 text-blue-500" />
                    Mid — coding, general
                  </SelectItem>
                  <SelectItem value="low">
                    <Search className="mr-1 inline h-3 w-3 text-emerald-500" />
                    Low — research, summarize
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Context window */}
          <div>
            <label htmlFor="model-ctx" className="text-xs font-medium text-muted-foreground mb-1 block">
              Context Window (tokens)
            </label>
            <Input
              id="model-ctx"
              type="number"
              value={form.contextWindow}
              onChange={(e) => update('contextWindow', parseInt(e.target.value, 10) || 0)}
              className="font-mono text-xs"
            />
          </div>

          {/* Cost */}
          <div className="grid gap-3 grid-cols-2">
            <div>
              <label htmlFor="model-cost-in" className="text-xs font-medium text-muted-foreground mb-1 block">
                Cost Input ($/1K tok)
              </label>
              <Input
                id="model-cost-in"
                type="number"
                step="0.01"
                value={form.costInput}
                onChange={(e) => update('costInput', parseFloat(e.target.value) || 0)}
                className="font-mono text-xs"
              />
            </div>
            <div>
              <label htmlFor="model-cost-out" className="text-xs font-medium text-muted-foreground mb-1 block">
                Cost Output ($/1K tok)
              </label>
              <Input
                id="model-cost-out"
                type="number"
                step="0.01"
                value={form.costOutput}
                onChange={(e) => update('costOutput', parseFloat(e.target.value) || 0)}
                className="font-mono text-xs"
              />
            </div>
          </div>

          {/* Capabilities */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
              Capabilities
            </label>
            <CapabilityChips
              selected={form.capabilities}
              onChange={(caps) => update('capabilities', caps)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!valid}
            onClick={() => {
              onSave(form)
              onOpenChange(false)
            }}
          >
            Save Model
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function ModelConfigPanel() {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [models, setModels] = useState<ModelEntry[]>([])
  const [dirty, setDirty] = useState(false)

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editIndex, setEditIndex] = useState<number | null>(null)

  const { data: configData } = useQuery({
    queryKey: ['config'],
    queryFn: () => rpc.config.get(),
    select: (d) => d as ConfigData,
  })

  // Sync from server
  useEffect(() => {
    if (!configData?.raw || dirty) return
    const cfg = parseConfig(configData.raw)
    setModels(getModelsFromConfig(cfg))
  }, [configData?.raw]) // eslint-disable-line react-hooks/exhaustive-deps

  // Save
  const saveMut = useMutation({
    mutationFn: async () => {
      const latest = (await rpc.config.get()) as ConfigData
      const cfg = parseConfig(latest.raw)
      const agents = (cfg.agents ?? {}) as Record<string, unknown>
      const orch = (agents.orchestrator ?? {}) as Record<string, unknown>

      const serialized = models.map((m) => ({
        model: m.model,
        provider: m.provider,
        capabilities: m.capabilities,
        tier: m.tier,
        costInput: m.costInput,
        costOutput: m.costOutput,
        contextWindow: m.contextWindow,
      }))

      const updatedCfg = {
        ...cfg,
        agents: {
          ...agents,
          orchestrator: {
            ...orch,
            models: serialized,
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
      void qc.invalidateQueries({ queryKey: ['orchestrator-models'] })
      setDirty(false)
      toast.success('Model configuration saved')
    },
    onError: (err) => {
      toast.error(`Save failed: ${err.message}`)
    },
  })

  // CRUD handlers
  const handleAdd = () => {
    setEditIndex(null)
    setDialogOpen(true)
  }

  const handleEdit = (index: number) => {
    setEditIndex(index)
    setDialogOpen(true)
  }

  const handleDelete = (index: number) => {
    setModels((prev) => prev.filter((_, i) => i !== index))
    setDirty(true)
  }

  const handleDialogSave = (model: ModelEntry) => {
    if (editIndex !== null) {
      setModels((prev) => prev.map((m, i) => (i === editIndex ? model : m)))
    } else {
      setModels((prev) => [...prev, model])
    }
    setDirty(true)
  }

  // Stats
  const byTier = {
    high: models.filter((m) => m.tier === 'high').length,
    mid: models.filter((m) => m.tier === 'mid').length,
    low: models.filter((m) => m.tier === 'low').length,
  }
  const freeCount = models.filter((m) => m.costInput === 0 && m.costOutput === 0).length

  return (
    <div className="rounded-xl border border-border bg-card">
      {/* Header */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 p-4 text-left cursor-pointer hover:bg-accent/5 transition-colors rounded-xl"
      >
        <Cpu className="h-5 w-5 text-muted-foreground" />
        <div className="flex-1">
          <h3 className="text-sm font-medium">Model Configuration</h3>
          <p className="text-xs text-muted-foreground">
            Configure models available for orchestrator routing
          </p>
        </div>
        {models.length > 0 && (
          <div className="flex items-center gap-1.5">
            <Badge variant="outline" className="text-[10px]">
              {models.length} model{models.length !== 1 ? 's' : ''}
            </Badge>
            {freeCount > 0 && (
              <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-500 border-emerald-500/30">
                {freeCount} free
              </Badge>
            )}
          </div>
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
          {/* Tier summary */}
          {models.length > 0 && (
            <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
              <span className="text-amber-500">{byTier.high} high</span>
              <span className="text-blue-500">{byTier.mid} mid</span>
              <span className="text-emerald-500">{byTier.low} low</span>
              <span className="ml-auto">
                Orchestrator routes tasks to the best model per capability + tier
              </span>
            </div>
          )}

          {/* Model list */}
          {models.length === 0 && (
            <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
              No custom models configured. Orchestrator will use built-in defaults
              (Anthropic, OpenAI, DeepSeek, Gemini).
            </p>
          )}

          <div className="space-y-2">
            {models.map((m, i) => (
              <ModelCard
                key={`${m.model}-${i}`}
                model={m}
                onEdit={() => handleEdit(i)}
                onDelete={() => handleDelete(i)}
              />
            ))}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between pt-2">
            <Button variant="outline" size="sm" onClick={handleAdd}>
              <Plus className="mr-1 h-3.5 w-3.5" />
              Add Model
            </Button>

            <Button
              size="sm"
              onClick={() => saveMut.mutate()}
              disabled={saveMut.isPending || !dirty}
              className={cn(!dirty && 'opacity-50')}
            >
              {saveMut.isPending ? 'Saving\u2026' : 'Save Models'}
            </Button>
          </div>
        </div>
      )}

      {/* Dialog */}
      <ModelDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        initial={editIndex !== null ? models[editIndex] : emptyModel()}
        onSave={handleDialogSave}
        title={editIndex !== null ? 'Edit Model' : 'Add Model'}
      />
    </div>
  )
}
