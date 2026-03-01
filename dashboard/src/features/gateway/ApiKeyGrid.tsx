import { useState, useCallback } from 'react'
import {
  Globe, Zap, Brain, Sparkles, Bot, Cpu, Cloud, Eye, EyeOff,
  Check, X, Pencil, Trash2, Plus, Server, Loader2,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { StatusDot } from '@/components/common/StatusDot'
import { Skeleton } from '@/components/ui/skeleton'
import { rpc } from '@/ws/rpc'

// ---------------------------------------------------------------------------
// Provider definitions — API key based only
// ---------------------------------------------------------------------------

interface ApiProviderDef {
  name: string        // config field name (e.g. "dashscope")
  label: string
  icon: ReactNode
  tier: 'gateway' | 'standard' | 'local'
  description: string
  hasApiBase?: boolean // show API base URL field
}

const API_PROVIDERS: ApiProviderDef[] = [
  // Gateways
  { name: 'openrouter', label: 'OpenRouter', icon: <Globe className="h-5 w-5" />, tier: 'gateway', description: 'Universal gateway — any model' },
  { name: 'aihubmix', label: 'AiHubMix', icon: <Globe className="h-5 w-5" />, tier: 'gateway', description: 'OpenAI-compatible gateway', hasApiBase: true },
  { name: 'siliconflow', label: 'SiliconFlow', icon: <Globe className="h-5 w-5" />, tier: 'gateway', description: 'Chinese model gateway', hasApiBase: true },
  { name: 'volcengine', label: 'VolcEngine', icon: <Globe className="h-5 w-5" />, tier: 'gateway', description: 'ByteDance model gateway', hasApiBase: true },
  // Standard
  { name: 'anthropic', label: 'Anthropic', icon: <Bot className="h-5 w-5" />, tier: 'standard', description: 'Claude API (direct)' },
  { name: 'openai', label: 'OpenAI', icon: <Cpu className="h-5 w-5" />, tier: 'standard', description: 'GPT models (direct)' },
  { name: 'deepseek', label: 'DeepSeek', icon: <Brain className="h-5 w-5" />, tier: 'standard', description: 'DeepSeek R1/V3' },
  { name: 'gemini', label: 'Gemini', icon: <Sparkles className="h-5 w-5" />, tier: 'standard', description: 'Google Gemini API' },
  { name: 'dashscope', label: 'DashScope', icon: <Cloud className="h-5 w-5" />, tier: 'standard', description: 'Alibaba Qwen models' },
  { name: 'moonshot', label: 'Moonshot', icon: <Zap className="h-5 w-5" />, tier: 'standard', description: 'Kimi models' },
  { name: 'zhipu', label: 'Zhipu AI', icon: <Brain className="h-5 w-5" />, tier: 'standard', description: 'GLM models' },
  { name: 'minimax', label: 'MiniMax', icon: <Zap className="h-5 w-5" />, tier: 'standard', description: 'MiniMax models' },
  { name: 'groq', label: 'Groq', icon: <Zap className="h-5 w-5" />, tier: 'standard', description: 'Fast inference (Whisper/LLM)' },
  // Local
  { name: 'vllm', label: 'vLLM/Local', icon: <Server className="h-5 w-5" />, tier: 'local', description: 'Self-hosted models', hasApiBase: true },
  // Custom
  { name: 'custom', label: 'Custom', icon: <Server className="h-5 w-5" />, tier: 'local', description: 'Any OpenAI-compatible endpoint', hasApiBase: true },
]

const TIER_STYLES: Record<string, string> = {
  gateway: 'border-primary/30 text-primary',
  standard: 'border-warning/30 text-warning',
  local: 'border-success/30 text-success',
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ConfigValue = string | number | boolean | null | Record<string, unknown>

interface ProviderConfigData {
  apiKey?: string
  api_key?: string
  apiBase?: string
  api_base?: string
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ApiKeyGrid() {
  const queryClient = useQueryClient()

  const { data: config, isLoading } = useQuery({
    queryKey: ['config-raw'],
    queryFn: async () => {
      const raw = await rpc.config.get() as { raw?: string } | Record<string, ConfigValue>
      if (raw && 'raw' in raw && typeof raw.raw === 'string') {
        try { return JSON.parse(raw.raw) as Record<string, unknown> } catch { return {} }
      }
      return raw as Record<string, unknown>
    },
    refetchInterval: 60_000,
  })

  const providers = config?.['providers'] as Record<string, ProviderConfigData> | undefined

  const saveMutation = useMutation({
    mutationFn: async (patch: { provider: string; apiKey: string; apiBase?: string }) => {
      // Read current config, merge, save
      const rawRes = await rpc.config.get() as { raw?: string; hash?: string }
      const currentRaw = rawRes.raw ?? '{}'
      const currentHash = rawRes.hash
      const parsed = JSON.parse(currentRaw) as Record<string, unknown>

      if (!parsed.providers) parsed.providers = {}
      const provs = parsed.providers as Record<string, Record<string, string>>
      if (!provs[patch.provider]) provs[patch.provider] = {}

      if (patch.apiKey) {
        provs[patch.provider].apiKey = patch.apiKey
      } else {
        delete provs[patch.provider].apiKey
        delete provs[patch.provider].api_key
      }

      if (patch.apiBase !== undefined) {
        if (patch.apiBase) {
          provs[patch.provider].apiBase = patch.apiBase
        } else {
          delete provs[patch.provider].apiBase
          delete provs[patch.provider].api_base
        }
      }

      // Clean empty provider objects
      if (Object.keys(provs[patch.provider]).length === 0) {
        delete provs[patch.provider]
      }

      await rpc.config.set({ raw: JSON.stringify(parsed, null, 2), baseHash: currentHash })
    },
    onSuccess: () => {
      toast.success('API key saved')
      void queryClient.invalidateQueries({ queryKey: ['config-raw'] })
    },
    onError: (err: unknown) => {
      toast.error('Save failed', { description: err instanceof Error ? err.message : 'Unknown error' })
    },
  })

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-32 rounded-xl" />
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {API_PROVIDERS.map((def) => {
        const cfg = providers?.[def.name]
        const apiKey = cfg?.apiKey ?? cfg?.api_key ?? ''
        const apiBase = cfg?.apiBase ?? cfg?.api_base ?? ''
        return (
          <ApiKeyCard
            key={def.name}
            def={def}
            apiKey={apiKey}
            apiBase={apiBase}
            onSave={(key, base) => saveMutation.mutate({ provider: def.name, apiKey: key, apiBase: base })}
            isSaving={saveMutation.isPending}
          />
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------

interface ApiKeyCardProps {
  def: ApiProviderDef
  apiKey: string
  apiBase: string
  onSave: (apiKey: string, apiBase?: string) => void
  isSaving: boolean
}

function ApiKeyCard({ def, apiKey, apiBase, onSave, isSaving }: ApiKeyCardProps) {
  const [editing, setEditing] = useState(false)
  const [keyValue, setKeyValue] = useState(apiKey)
  const [baseValue, setBaseValue] = useState(apiBase)
  const [showKey, setShowKey] = useState(false)

  const hasKey = apiKey.length > 0
  const masked = apiKey ? `${apiKey.slice(0, 6)}${'•'.repeat(8)}` : ''

  const handleEdit = useCallback(() => {
    setKeyValue(apiKey)
    setBaseValue(apiBase)
    setEditing(true)
    setShowKey(false)
  }, [apiKey, apiBase])

  const handleSave = useCallback(() => {
    onSave(keyValue.trim(), def.hasApiBase ? baseValue.trim() : undefined)
    setEditing(false)
  }, [keyValue, baseValue, def.hasApiBase, onSave])

  const handleRemove = useCallback(() => {
    onSave('', def.hasApiBase ? '' : undefined)
    setEditing(false)
    setKeyValue('')
    setBaseValue('')
  }, [def.hasApiBase, onSave])

  return (
    <Card className="relative overflow-hidden hover:border-primary/30 transition-colors">
      <CardContent className="flex items-start gap-4 p-5">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-muted/50 text-muted-foreground">
          {def.icon}
        </div>

        <div className="flex-1 min-w-0 space-y-2">
          {/* Header */}
          <div className="flex items-center gap-2">
            <span className="font-semibold truncate">{def.label}</span>
            <Badge variant="outline" className={`text-[10px] ${TIER_STYLES[def.tier] ?? ''}`}>
              {def.tier}
            </Badge>
          </div>

          <p className="text-sm text-muted-foreground line-clamp-1">{def.description}</p>

          {/* Status / Edit row */}
          {editing ? (
            <div className="space-y-2 pt-1">
              <div className="relative">
                <Input
                  type={showKey ? 'text' : 'password'}
                  value={keyValue}
                  onChange={(e) => setKeyValue(e.target.value)}
                  placeholder="API key"
                  className="pr-9 font-mono text-xs h-8"
                  autoFocus
                />
                <button
                  type="button"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
                  onClick={() => setShowKey((v) => !v)}
                  aria-label={showKey ? 'Hide' : 'Show'}
                >
                  {showKey ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                </button>
              </div>
              {def.hasApiBase && (
                <Input
                  value={baseValue}
                  onChange={(e) => setBaseValue(e.target.value)}
                  placeholder="API base URL (optional)"
                  className="font-mono text-xs h-8"
                />
              )}
              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-6 text-xs px-2"
                  onClick={handleSave}
                  disabled={isSaving}
                  aria-label="Save API key"
                >
                  {isSaving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-xs px-2"
                  onClick={() => setEditing(false)}
                  aria-label="Cancel"
                >
                  <X className="h-3 w-3" />
                </Button>
                {hasKey && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-xs px-2 ml-auto text-destructive hover:text-destructive"
                    onClick={handleRemove}
                    aria-label="Remove API key"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 pt-0.5">
              {hasKey ? (
                <>
                  <StatusDot status="online" />
                  <span className="text-xs font-mono text-muted-foreground truncate">{masked}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto h-7 text-xs text-muted-foreground"
                    onClick={handleEdit}
                    aria-label="Edit API key"
                  >
                    <Pencil className="mr-1 h-3 w-3" />
                    Edit
                  </Button>
                </>
              ) : (
                <>
                  <StatusDot status="offline" />
                  <span className="text-xs text-muted-foreground">No API key</span>
                  <Button
                    variant="outline"
                    size="sm"
                    className="ml-auto h-7 text-xs"
                    onClick={handleEdit}
                    aria-label="Add API key"
                  >
                    <Plus className="mr-1 h-3 w-3" />
                    Add Key
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
