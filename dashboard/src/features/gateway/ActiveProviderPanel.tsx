import { useState, useMemo } from 'react'
import { Cpu, AlertTriangle, Check, ChevronDown, Info } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { rpc } from '@/ws/rpc'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ConfigValue = string | number | boolean | null | Record<string, unknown>

interface ProviderInfo {
  model: string
  provider: string         // "auto" | "anthropic" | "claude_cli" | etc.
  providerType: 'cli' | 'api' | 'oauth' | 'custom' | 'unknown'
  label: string
  toolMode: string         // how tools are handled
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resolveProviderInfo(config: Record<string, unknown>): ProviderInfo {
  const agents = config?.agents as Record<string, unknown> | undefined
  const defaults = agents?.defaults as Record<string, unknown> | undefined
  const model = (defaults?.model as string) ?? 'unknown'
  const provider = (defaults?.provider as string) ?? 'auto'

  // Determine provider type from model name
  if (model.startsWith('claude-cli/') || provider === 'claude_cli') {
    return {
      model,
      provider,
      providerType: 'cli',
      label: 'Claude CLI',
      toolMode: 'CLI subprocess — tools injected as text prompt, MCP managed by Claude',
    }
  }
  if (model.startsWith('openai-codex/') || provider === 'openai_codex') {
    return {
      model,
      provider,
      providerType: 'oauth',
      label: 'OpenAI Codex',
      toolMode: 'OAuth API — NanoBot controls tools natively',
    }
  }
  if (provider === 'custom') {
    return {
      model,
      provider,
      providerType: 'custom',
      label: 'Custom Endpoint',
      toolMode: 'Direct API — NanoBot controls tools natively',
    }
  }

  // API provider via LiteLLM
  const prefix = model.split('/')[0]
  const LABELS: Record<string, string> = {
    anthropic: 'Anthropic API', openai: 'OpenAI API', deepseek: 'DeepSeek',
    gemini: 'Gemini API', dashscope: 'DashScope', moonshot: 'Moonshot',
    openrouter: 'OpenRouter', groq: 'Groq', zhipu: 'Zhipu AI',
    minimax: 'MiniMax', aihubmix: 'AiHubMix', siliconflow: 'SiliconFlow',
    volcengine: 'VolcEngine',
  }
  return {
    model,
    provider,
    providerType: 'api',
    label: LABELS[prefix] ?? LABELS[provider] ?? (prefix || 'LiteLLM'),
    toolMode: 'LiteLLM API — NanoBot controls tools natively via function calling',
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ActiveProviderPanel() {
  const queryClient = useQueryClient()
  const [showSwitcher, setShowSwitcher] = useState(false)

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

  const info = useMemo(() => config ? resolveProviderInfo(config) : null, [config])

  const switchMutation = useMutation({
    mutationFn: async (newModel: string) => {
      const rawRes = await rpc.config.get() as { raw?: string; hash?: string }
      const currentRaw = rawRes.raw ?? '{}'
      const currentHash = rawRes.hash
      const parsed = JSON.parse(currentRaw) as Record<string, unknown>

      if (!parsed.agents) parsed.agents = {}
      const agents = parsed.agents as Record<string, unknown>
      if (!agents.defaults) agents.defaults = {}
      const defaults = agents.defaults as Record<string, string>
      defaults.model = newModel

      await rpc.config.set({
        patch: {
          raw: JSON.stringify(parsed, null, 2),
          baseHash: currentHash,
        } as unknown as Record<string, unknown>,
      })
    },
    onSuccess: () => {
      toast.success('Provider switched — restart NanoBot to apply')
      void queryClient.invalidateQueries({ queryKey: ['config-raw'] })
      setShowSwitcher(false)
    },
    onError: (err: unknown) => {
      toast.error('Switch failed', { description: err instanceof Error ? err.message : 'Unknown error' })
    },
  })

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-5">
          <Skeleton className="h-12 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (!info) return null

  const isCli = info.providerType === 'cli'

  return (
    <Card className={isCli ? 'border-warning/30' : ''}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Cpu className="h-4 w-4" />
          Active Provider
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Current model + provider info */}
        <div className="flex items-center gap-3 flex-wrap">
          <Badge variant="secondary" className="font-mono text-xs">
            {info.model}
          </Badge>
          <Badge variant="outline" className={`text-xs ${isCli ? 'border-warning/40 text-warning' : 'border-success/40 text-success'}`}>
            {info.label}
          </Badge>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto h-7 text-xs"
            onClick={() => setShowSwitcher((v) => !v)}
            aria-label="Switch provider"
          >
            Switch
            <ChevronDown className="ml-1 h-3 w-3" />
          </Button>
        </div>

        {/* Tool mode info */}
        <div className="flex items-start gap-2 rounded-lg bg-muted/30 px-3 py-2.5">
          {isCli ? (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          ) : (
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" />
          )}
          <div className="min-w-0">
            <p className="text-xs font-medium">
              {isCli ? 'CLI Mode — Limited Tool Control' : 'API Mode — Full Tool Control'}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">{info.toolMode}</p>
          </div>
        </div>

        {isCli && (
          <div className="flex items-start gap-2 rounded-lg bg-warning/5 border border-warning/20 px-3 py-2.5">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <p className="text-xs text-muted-foreground">
              Claude CLI uses its own MCP plugins instead of NanoBot's tool registry.
              Switch to an API provider for full NanoBot tool control.
            </p>
          </div>
        )}

        {/* Quick switcher */}
        {showSwitcher && (
          <QuickSwitcher
            currentModel={info.model}
            config={config ?? {}}
            onSwitch={(model) => switchMutation.mutate(model)}
            isSwitching={switchMutation.isPending}
          />
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Quick Switcher
// ---------------------------------------------------------------------------

interface QuickSwitcherProps {
  currentModel: string
  config: Record<string, unknown>
  onSwitch: (model: string) => void
  isSwitching: boolean
}

interface SwitchOption {
  model: string
  label: string
  available: boolean
  reason?: string
}

function QuickSwitcher({ currentModel, config, onSwitch, isSwitching }: QuickSwitcherProps) {
  const providers = config?.providers as Record<string, Record<string, string>> | undefined

  const options: SwitchOption[] = useMemo(() => {
    const opts: SwitchOption[] = []

    // Claude CLI (always available if claude is installed)
    opts.push({
      model: 'claude-cli/sonnet',
      label: 'Claude CLI (Sonnet)',
      available: true,
    })
    opts.push({
      model: 'claude-cli/opus',
      label: 'Claude CLI (Opus)',
      available: true,
    })

    // API providers — check if key is configured
    const apiProviders: Array<{ name: string; model: string; label: string }> = [
      { name: 'anthropic', model: 'anthropic/claude-sonnet-4-5', label: 'Anthropic API (Sonnet 4.5)' },
      { name: 'openai', model: 'openai/gpt-4.1', label: 'OpenAI (GPT-4.1)' },
      { name: 'deepseek', model: 'deepseek/deepseek-chat', label: 'DeepSeek Chat' },
      { name: 'gemini', model: 'gemini/gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
      { name: 'dashscope', model: 'dashscope/qwen-coder-plus-latest', label: 'DashScope (Qwen Coder+)' },
      { name: 'openrouter', model: 'openrouter/anthropic/claude-sonnet-4', label: 'OpenRouter (Claude Sonnet)' },
      { name: 'moonshot', model: 'moonshot/kimi-k2.5', label: 'Moonshot (Kimi K2.5)' },
      { name: 'groq', model: 'groq/llama-3.3-70b-versatile', label: 'Groq (Llama 3.3 70B)' },
    ]

    for (const p of apiProviders) {
      const key = providers?.[p.name]?.apiKey ?? providers?.[p.name]?.api_key ?? ''
      opts.push({
        model: p.model,
        label: p.label,
        available: key.length > 0,
        reason: key.length > 0 ? undefined : 'No API key',
      })
    }

    return opts
  }, [providers])

  return (
    <div className="border border-border rounded-lg divide-y divide-border max-h-64 overflow-y-auto">
      {options.map((opt) => {
        const isCurrent = currentModel === opt.model
        return (
          <button
            key={opt.model}
            type="button"
            className="flex items-center gap-3 w-full px-3 py-2 text-left hover:bg-muted/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            disabled={isCurrent || !opt.available || isSwitching}
            onClick={() => onSwitch(opt.model)}
          >
            <span className="text-xs font-medium flex-1 truncate">{opt.label}</span>
            <span className="font-mono text-[10px] text-muted-foreground truncate max-w-[200px]">
              {opt.model}
            </span>
            {isCurrent && (
              <Badge variant="outline" className="text-[10px] border-primary/40 text-primary shrink-0">
                Active
              </Badge>
            )}
            {!opt.available && opt.reason && (
              <Badge variant="outline" className="text-[10px] border-destructive/40 text-destructive shrink-0">
                {opt.reason}
              </Badge>
            )}
          </button>
        )
      })}
    </div>
  )
}
