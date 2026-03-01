import { useState } from 'react'
import { ChevronDown, Trash2 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { rpc } from '@/ws/rpc'
import type { SubAgentRoleConfig } from '@/types/skills'
import type { ModelInfo } from '@/types/orchestrator'
import {
  THINKING_STYLE_OPTIONS,
  PERSISTENCE_OPTIONS,
  RESPONSE_LENGTH_OPTIONS,
} from './SubAgentPresets'

const INHERIT_VALUE = '__inherit__'

interface SubAgentRoleCardProps {
  roleId: string
  config: SubAgentRoleConfig
  activeModel?: string
  onUpdate: (roleId: string, patch: Partial<SubAgentRoleConfig>) => void
  onDelete?: (roleId: string) => void
}

export function SubAgentRoleCard({
  roleId,
  config,
  activeModel,
  onUpdate,
  onDelete,
}: SubAgentRoleCardProps) {
  const [personaOpen, setPersonaOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const { data: modelsData } = useQuery({
    queryKey: ['orchestrator', 'models'],
    queryFn: () => rpc.orchestrator.models(),
    staleTime: 60_000,
  })
  const availableModels: ModelInfo[] = modelsData?.models ?? []
  const mainModelShort = activeModel?.split('/').pop() ?? activeModel ?? 'default'

  const display = config.displayName || roleId
  const icon = config.icon || '🤖'

  return (
    <Card className="space-y-3 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg" role="img" aria-hidden="true">
            {icon}
          </span>
          <span className="text-sm font-semibold">{display}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {config.builtin && (
            <Badge variant="secondary" className="text-[9px]">
              Built-in
            </Badge>
          )}
          {!config.builtin && onDelete && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-muted-foreground hover:text-destructive"
              onClick={() => onDelete(roleId)}
              aria-label={`Delete ${display} role`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Description */}
      {config.description && (
        <p className="text-xs text-muted-foreground">{config.description}</p>
      )}

      {/* Strengths */}
      {config.strengths.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {config.strengths.map((s) => (
            <Badge key={s} variant="outline" className="text-[9px]">
              {s}
            </Badge>
          ))}
        </div>
      )}

      {/* Preset Selectors */}
      <div className="space-y-2">
        <div className="space-y-1">
          <Label className="text-xs">Thinking</Label>
          <Select
            value={config.thinkingStyle || 'balanced'}
            onValueChange={(v) => onUpdate(roleId, { thinkingStyle: v })}
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {THINKING_STYLE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  <span className="flex items-center gap-2">
                    <span>{opt.label}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {opt.description}
                    </span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label className="text-xs">Persistence</Label>
            <Select
              value={config.persistence || 'normal'}
              onValueChange={(v) => onUpdate(roleId, { persistence: v })}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PERSISTENCE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    <span className="flex items-center gap-2">
                      <span>{opt.label}</span>
                      <span className="text-[10px] text-muted-foreground">
                        {opt.description}
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Response</Label>
            <Select
              value={config.responseLength || 'normal'}
              onValueChange={(v) => onUpdate(roleId, { responseLength: v })}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RESPONSE_LENGTH_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    <span className="flex items-center gap-2">
                      <span>{opt.label}</span>
                      <span className="text-[10px] text-muted-foreground">
                        {opt.description}
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Model Override */}
        <div className="space-y-1">
          <Label className="text-xs">Model</Label>
          <Select
            value={config.model || INHERIT_VALUE}
            onValueChange={(v) => onUpdate(roleId, { model: v === INHERIT_VALUE ? '' : v })}
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={INHERIT_VALUE}>
                <span className="text-muted-foreground">Inherit main</span>
                <span className="ml-1.5 font-mono text-[10px] text-muted-foreground/70">
                  ({mainModelShort})
                </span>
              </SelectItem>
              {availableModels.map((m) => (
                <SelectItem key={m.model} value={m.model}>
                  <span className="flex items-center gap-1.5">
                    <span>{m.model.split('/').pop()}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {m.tier} · {m.provider}
                    </span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Persona (collapsible) */}
      <Collapsible open={personaOpen} onOpenChange={setPersonaOpen}>
        <CollapsibleTrigger className="flex w-full cursor-pointer items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <ChevronDown
            className={`h-3 w-3 transition-transform ${personaOpen ? '' : '-rotate-90'}`}
          />
          Persona
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-2">
          <Textarea
            placeholder="Custom personality, behavior, communication style..."
            defaultValue={config.persona}
            onBlur={(e) => {
              if (e.target.value !== config.persona) {
                onUpdate(roleId, { persona: e.target.value })
              }
            }}
            className="min-h-[80px] text-xs"
          />
        </CollapsibleContent>
      </Collapsible>

      {/* Advanced (collapsible) */}
      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <CollapsibleTrigger className="flex w-full cursor-pointer items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <ChevronDown
            className={`h-3 w-3 transition-transform ${advancedOpen ? '' : '-rotate-90'}`}
          />
          Advanced
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-2 pt-2">
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label className="text-[10px]">Temperature</Label>
              <Input
                type="number"
                min={0}
                max={2}
                step={0.1}
                defaultValue={config.temperature || ''}
                placeholder="auto"
                onBlur={(e) => {
                  const v = parseFloat(e.target.value)
                  onUpdate(roleId, { temperature: isNaN(v) ? 0 : v })
                }}
                className="h-7 text-[11px]"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-[10px]">Iterations</Label>
              <Input
                type="number"
                min={1}
                max={40}
                defaultValue={config.maxIterations || ''}
                placeholder="auto"
                onBlur={(e) => {
                  const v = parseInt(e.target.value)
                  onUpdate(roleId, { maxIterations: isNaN(v) ? 0 : v })
                }}
                className="h-7 text-[11px]"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-[10px]">Max Tokens</Label>
              <Input
                type="number"
                min={256}
                max={32768}
                step={256}
                defaultValue={config.maxTokens || ''}
                placeholder="auto"
                onBlur={(e) => {
                  const v = parseInt(e.target.value)
                  onUpdate(roleId, { maxTokens: isNaN(v) ? 0 : v })
                }}
                className="h-7 text-[11px]"
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label className="text-[10px]">Tools (comma-separated)</Label>
            <Input
              placeholder="(role default)"
              defaultValue={config.tools.join(', ')}
              onBlur={(e) => {
                const tools = e.target.value
                  .split(',')
                  .map((t) => t.trim())
                  .filter(Boolean)
                onUpdate(roleId, { tools })
              }}
              className="h-7 text-[11px]"
            />
          </div>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  )
}
