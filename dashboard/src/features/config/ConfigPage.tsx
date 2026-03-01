import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, RefreshCw, AlertTriangle, Zap } from 'lucide-react'
import { toast } from 'sonner'
import { rpc } from '@/ws/rpc'
import { PageHeader } from '@/components/common/PageHeader'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfigFormView } from './ConfigFormView'
import { ConfigRawView } from './ConfigRawView'

type ConfigValue = string | number | boolean | Record<string, unknown> | unknown[]

export function ConfigPage() {
  const queryClient = useQueryClient()
  const [rawJson, setRawJson] = useState<string | null>(null)
  const [formConfig, setFormConfig] = useState<Record<string, ConfigValue> | null>(null)
  const [jsonParseError, setJsonParseError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'form' | 'raw'>('form')

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const { data: remoteConfig, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: () => rpc.config.get(),
    select: (data) => {
      const d = data as { raw?: string } | Record<string, ConfigValue>
      if (d && 'raw' in d && typeof d.raw === 'string') {
        try { return JSON.parse(d.raw) as Record<string, ConfigValue> } catch { return {} }
      }
      return d as Record<string, ConfigValue>
    },
  })

  // Sync remote into local state on first load (render-phase guard is safe here
  // because formConfig starts null and is set only once)
  if (remoteConfig && !formConfig) {
    setFormConfig(remoteConfig)
    setRawJson(JSON.stringify(remoteConfig, null, 2))
  }

  // ---------------------------------------------------------------------------
  // Mutations
  // ---------------------------------------------------------------------------

  const saveMutation = useMutation({
    mutationFn: async (apply: boolean) => {
      let patch: Record<string, ConfigValue>

      if (activeTab === 'raw') {
        try {
          patch = JSON.parse(rawJson ?? '{}') as Record<string, ConfigValue>
        } catch (e) {
          throw new Error('Invalid JSON — please fix syntax errors before saving')
        }
      } else {
        patch = formConfig ?? {}
      }

      const rawRes = await rpc.config.get() as { raw?: string; hash?: string }
      await rpc.config.set({
        raw: JSON.stringify(patch, null, 2),
        baseHash: rawRes.hash,
      })
      if (apply) {
        await rpc.config.apply()
      }
      return apply
    },
    onSuccess: (applied: boolean) => {
      toast.success(applied ? 'Config saved & applied' : 'Config saved', {
        description: applied ? 'Changes are now active' : 'Restart the agent to apply changes',
      })
      void queryClient.invalidateQueries({ queryKey: ['config'] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Save failed'
      toast.error('Save failed', { description: msg })
    },
  })

  // ---------------------------------------------------------------------------
  // Tab sync
  // ---------------------------------------------------------------------------

  function handleTabChange(tab: string) {
    const t = tab as 'form' | 'raw'
    if (t === 'raw' && formConfig) {
      setRawJson(JSON.stringify(formConfig, null, 2))
    }
    if (t === 'form' && rawJson) {
      try {
        setFormConfig(JSON.parse(rawJson) as Record<string, ConfigValue>)
        setJsonParseError(null)
      } catch {
        setJsonParseError('Invalid JSON — fix errors before switching to Form view')
      }
    }
    setActiveTab(t)
  }

  function handleRawChange(value: string) {
    setRawJson(value)
    try {
      setFormConfig(JSON.parse(value) as Record<string, ConfigValue>)
      setJsonParseError(null)
    } catch {
      setJsonParseError('Invalid JSON')
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const isSaving = saveMutation.isPending

  return (
    <ErrorBoundary>
      <PageHeader
        title="Config"
        description="Edit NanoBot configuration"
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => saveMutation.mutate(false)}
              disabled={isSaving || !!jsonParseError}
            >
              {isSaving ? (
                <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="mr-1.5 h-3.5 w-3.5" />
              )}
              Save
            </Button>
            <Button
              size="sm"
              onClick={() => saveMutation.mutate(true)}
              disabled={isSaving || !!jsonParseError}
            >
              {isSaving ? (
                <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Zap className="mr-1.5 h-3.5 w-3.5" />
              )}
              Save & Apply
            </Button>
          </div>
        }
      />

      {jsonParseError && (
        <div className="mb-4 flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {jsonParseError}
        </div>
      )}

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="mb-4">
          <TabsTrigger value="form">Form</TabsTrigger>
          <TabsTrigger value="raw">Raw JSON</TabsTrigger>
        </TabsList>

        <TabsContent value="form">
          {isLoading || !formConfig ? (
            <div className="space-y-4">
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          ) : (
            <ConfigFormView
              config={formConfig}
              onChange={(patch) => setFormConfig(patch)}
            />
          )}
        </TabsContent>

        <TabsContent value="raw">
          {isLoading ? (
            <Skeleton className="h-96 w-full" />
          ) : (
            <ConfigRawView
              value={rawJson ?? ''}
              onChange={handleRawChange}
            />
          )}
        </TabsContent>
      </Tabs>
    </ErrorBoundary>
  )
}
