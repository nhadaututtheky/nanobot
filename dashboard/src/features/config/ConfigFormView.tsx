import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { ChevronDown, ChevronRight, Bot, Radio, Cpu, Globe, Wrench } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { NineRouterSection } from './NineRouterSection'
import { useState } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ConfigValue = string | number | boolean | Record<string, ConfigValue> | ConfigValue[]

interface ConfigFormViewProps {
  config: Record<string, ConfigValue>
  onChange: (patch: Record<string, ConfigValue>) => void
}

// ---------------------------------------------------------------------------
// Section config
// ---------------------------------------------------------------------------

const SECTION_META: Record<string, { label: string; icon: React.ReactNode }> = {
  agents: { label: 'Agents', icon: <Bot className="h-4 w-4" /> },
  channels: { label: 'Channels', icon: <Radio className="h-4 w-4" /> },
  providers: { label: 'Providers', icon: <Cpu className="h-4 w-4" /> },
  gateway: { label: 'Gateway', icon: <Globe className="h-4 w-4" /> },
  tools: { label: 'Tools', icon: <Wrench className="h-4 w-4" /> },
}

// ---------------------------------------------------------------------------
// FieldRow — renders a single leaf field
// ---------------------------------------------------------------------------

interface FieldRowProps {
  fieldKey: string
  value: ConfigValue
  onChange: (value: ConfigValue) => void
}

function FieldRow({ fieldKey, value, onChange }: FieldRowProps) {
  const label = fieldKey.replace(/_/g, ' ')

  if (typeof value === 'boolean') {
    return (
      <div className="flex items-center justify-between gap-4 py-1.5">
        <Label htmlFor={`field-${fieldKey}`} className="text-sm capitalize cursor-pointer">
          {label}
        </Label>
        <Switch
          id={`field-${fieldKey}`}
          checked={value}
          onCheckedChange={(checked) => onChange(checked)}
        />
      </div>
    )
  }

  if (typeof value === 'number') {
    return (
      <div className="space-y-1">
        <Label htmlFor={`field-${fieldKey}`} className="text-xs capitalize text-muted-foreground">
          {label}
        </Label>
        <Input
          id={`field-${fieldKey}`}
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="h-8 font-mono text-sm"
        />
      </div>
    )
  }

  if (typeof value === 'string') {
    return (
      <div className="space-y-1">
        <Label htmlFor={`field-${fieldKey}`} className="text-xs capitalize text-muted-foreground">
          {label}
        </Label>
        <Input
          id={`field-${fieldKey}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 font-mono text-sm"
        />
      </div>
    )
  }

  // Arrays and nested objects — show read-only JSON snippet
  return (
    <div className="space-y-1">
      <Label className="text-xs capitalize text-muted-foreground">{label}</Label>
      <pre className="rounded-md bg-muted/50 px-3 py-2 font-mono text-xs text-muted-foreground overflow-x-auto">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SectionCard — collapsible group
// ---------------------------------------------------------------------------

interface SectionCardProps {
  sectionKey: string
  data: Record<string, ConfigValue>
  onChange: (patch: Record<string, ConfigValue>) => void
}

function SectionCard({ sectionKey, data, onChange }: SectionCardProps) {
  const [open, setOpen] = useState(true)
  const meta = SECTION_META[sectionKey] ?? {
    label: sectionKey.charAt(0).toUpperCase() + sectionKey.slice(1),
    icon: <Wrench className="h-4 w-4" />,
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card>
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer select-none py-3 hover:bg-muted/30 transition-colors rounded-t-lg">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold">
              {meta.icon}
              {meta.label}
              <span className="ml-auto text-muted-foreground">
                {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </span>
            </CardTitle>
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className={cn('pt-0 grid gap-3', Object.keys(data).length > 4 ? 'sm:grid-cols-2' : '')}>
            {Object.entries(data).map(([k, v]) => (
              <FieldRow
                key={k}
                fieldKey={k}
                value={v}
                onChange={(newVal) => onChange({ ...data, [k]: newVal })}
              />
            ))}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}

// ---------------------------------------------------------------------------
// ConfigFormView
// ---------------------------------------------------------------------------

export function ConfigFormView({ config, onChange }: ConfigFormViewProps) {
  const { reset } = useForm()
  const [nineRouterEndpoint, setNineRouterEndpoint] = useState(
    () => {
      const providers = config['providers'] as Record<string, ConfigValue> | undefined
      const ninerouter = providers?.['ninerouter'] as Record<string, ConfigValue> | undefined
      return String(ninerouter?.['endpoint'] ?? 'http://localhost:20128/v1')
    }
  )

  useEffect(() => {
    reset()
  }, [config, reset])

  const topLevelSections = Object.entries(config).filter(
    ([, v]) => typeof v === 'object' && v !== null && !Array.isArray(v)
  ) as [string, Record<string, ConfigValue>][]

  function handleSectionChange(sectionKey: string, patch: Record<string, ConfigValue>) {
    onChange({ ...config, [sectionKey]: patch })
  }

  function handleNineRouterEndpoint(endpoint: string) {
    setNineRouterEndpoint(endpoint)
    const providers = (config['providers'] as Record<string, ConfigValue>) ?? {}
    const ninerouter = (providers['ninerouter'] as Record<string, ConfigValue>) ?? {}
    onChange({
      ...config,
      providers: {
        ...providers,
        ninerouter: { ...ninerouter, endpoint },
      },
    })
  }

  return (
    <div className="space-y-4">
      {topLevelSections.map(([key, data]) => (
        <SectionCard
          key={key}
          sectionKey={key}
          data={data}
          onChange={(patch) => handleSectionChange(key, patch)}
        />
      ))}
      <NineRouterSection
        endpoint={nineRouterEndpoint}
        onEndpointChange={handleNineRouterEndpoint}
      />
    </div>
  )
}
