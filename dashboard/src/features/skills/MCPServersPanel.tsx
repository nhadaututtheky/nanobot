import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Server, Plus, Trash2, Save, X } from 'lucide-react'
import { toast } from 'sonner'
import { rpc } from '@/ws/rpc'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import type { MCPServerConfig } from '@/types/skills'

interface ConfigData {
  raw: string
  hash: string
}

function parseConfig(raw: string): Record<string, unknown> {
  try {
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

function getMcpServers(config: Record<string, unknown>): Record<string, MCPServerConfig> {
  const tools = config.tools as Record<string, unknown> | undefined
  return (tools?.mcpServers ?? tools?.mcp_servers ?? {}) as Record<string, MCPServerConfig>
}

export function MCPServersPanel() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [newName, setNewName] = useState('')
  const [newCommand, setNewCommand] = useState('')
  const [newArgs, setNewArgs] = useState('')
  const [newUrl, setNewUrl] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['config', 'get'],
    queryFn: () => rpc.config.get() as Promise<ConfigData>,
    refetchInterval: 30_000,
  })

  const rawConfig = data?.raw ?? '{}'
  const baseHash = data?.hash ?? ''
  const config = parseConfig(rawConfig)
  const servers = getMcpServers(config)
  const serverEntries = Object.entries(servers)

  async function saveConfig(updatedConfig: Record<string, unknown>) {
    try {
      await rpc.config.set({
        raw: JSON.stringify(updatedConfig, null, 2),
        baseHash,
      })
      queryClient.invalidateQueries({ queryKey: ['config', 'get'] })
      toast.success('MCP servers updated')
    } catch (err) {
      toast.error(`Save failed: ${err instanceof Error ? err.message : 'unknown'}`)
    }
  }

  async function handleAdd() {
    if (!newName.trim()) return

    const server: Partial<MCPServerConfig> = {}
    if (newCommand) {
      server.command = newCommand
      server.args = newArgs.split(' ').filter(Boolean)
    }
    if (newUrl) {
      server.url = newUrl
    }

    const tools = (config.tools ?? {}) as Record<string, unknown>
    const currentServers = getMcpServers(config)
    const updatedConfig = {
      ...config,
      tools: {
        ...tools,
        mcpServers: { ...currentServers, [newName.trim()]: server },
      },
    }
    await saveConfig(updatedConfig)
    setShowAdd(false)
    setNewName('')
    setNewCommand('')
    setNewArgs('')
    setNewUrl('')
  }

  async function handleRemove(name: string) {
    const tools = (config.tools ?? {}) as Record<string, unknown>
    const currentServers = { ...getMcpServers(config) }
    delete currentServers[name]

    const updatedConfig = {
      ...config,
      tools: { ...tools, mcpServers: currentServers },
    }
    await saveConfig(updatedConfig)
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-16 rounded-lg" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {serverEntries.length === 0 && !showAdd && (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No MCP servers configured.
        </p>
      )}

      {serverEntries.map(([name, server]) => (
        <Card key={name} className="flex items-center justify-between gap-3 p-3">
          <div className="flex items-center gap-3 min-w-0">
            <Server className="h-4 w-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{name}</p>
              <p className="truncate text-xs text-muted-foreground">
                {server.url
                  ? server.url
                  : `${server.command} ${(server.args ?? []).join(' ')}`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Badge variant="outline" className="text-[10px]">
              {server.url ? 'HTTP' : 'stdio'}
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-destructive hover:text-destructive"
              onClick={() => handleRemove(name)}
              aria-label={`Remove MCP server ${name}`}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </Card>
      ))}

      {showAdd ? (
        <Card className="space-y-3 p-4">
          <div className="space-y-2">
            <Label htmlFor="mcp-name">Server Name</Label>
            <Input
              id="mcp-name"
              placeholder="e.g. neural-memory"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mcp-command">Command (stdio)</Label>
            <Input
              id="mcp-command"
              placeholder="e.g. npx"
              value={newCommand}
              onChange={(e) => setNewCommand(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mcp-args">Arguments</Label>
            <Input
              id="mcp-args"
              placeholder="e.g. -y @example/mcp-server"
              value={newArgs}
              onChange={(e) => setNewArgs(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mcp-url">Or HTTP URL</Label>
            <Input
              id="mcp-url"
              placeholder="e.g. http://localhost:3000/mcp"
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={handleAdd} disabled={!newName.trim()}>
              <Save className="mr-1 h-3 w-3" />
              Save
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowAdd(false)}
            >
              <X className="mr-1 h-3 w-3" />
              Cancel
            </Button>
          </div>
        </Card>
      ) : (
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowAdd(true)}
          className="w-full"
        >
          <Plus className="mr-1 h-3 w-3" />
          Add MCP Server
        </Button>
      )}
    </div>
  )
}
