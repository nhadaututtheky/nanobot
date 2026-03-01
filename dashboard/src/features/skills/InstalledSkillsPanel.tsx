import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Package, Trash2, ChevronDown, ChevronUp, Shield } from 'lucide-react'
import { toast } from 'sonner'
import { rpc } from '@/ws/rpc'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { SkillInfo } from '@/types/skills'

export function InstalledSkillsPanel() {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [skillContent, setSkillContent] = useState<string>('')
  const [removing, setRemoving] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['skills', 'status'],
    queryFn: () => rpc.skills.status(),
    refetchInterval: 30_000,
  })

  const skills: SkillInfo[] = data?.skills ?? []

  async function handleExpand(name: string) {
    if (expanded === name) {
      setExpanded(null)
      return
    }
    setExpanded(name)
    try {
      const res = await rpc.skills.read({ name })
      setSkillContent(res.content)
    } catch {
      setSkillContent('Failed to load skill content.')
    }
  }

  async function handleRemove(name: string) {
    setRemoving(name)
    try {
      await rpc.skills.uninstall({ name })
      toast.success(`Removed skill: ${name}`)
      queryClient.invalidateQueries({ queryKey: ['skills', 'status'] })
    } catch (err) {
      toast.error(`Failed to remove: ${err instanceof Error ? err.message : 'unknown error'}`)
    } finally {
      setRemoving(null)
    }
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    )
  }

  if (skills.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
        <Package className="mb-3 h-10 w-10 opacity-50" />
        <p className="text-sm">No skills installed yet.</p>
        <p className="text-xs">Search the marketplace below to get started.</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {skills.map((skill) => (
        <Card
          key={skill.key}
          className="flex flex-col gap-2 p-4 transition-colors hover:bg-accent/5"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-lg">{skill.emoji || '🔧'}</span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{skill.name}</p>
                {skill.description && (
                  <p className="truncate text-xs text-muted-foreground">{skill.description}</p>
                )}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {skill.source === 'builtin' ? (
                <Badge variant="secondary" className="text-[10px]">
                  <Shield className="mr-0.5 h-3 w-3" />
                  Built-in
                </Badge>
              ) : (
                <Badge variant="outline" className="text-[10px]">Workspace</Badge>
              )}
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {skill.always && (
              <Badge variant="default" className="text-[10px]">Always</Badge>
            )}
            {skill.available === false && (
              <Badge variant="destructive" className="text-[10px]">Unavailable</Badge>
            )}
            {skill.hasRequirements && (
              <Badge variant="outline" className="text-[10px]">Deps</Badge>
            )}
          </div>

          <div className="mt-auto flex items-center gap-1 pt-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => handleExpand(skill.name)}
              aria-label={expanded === skill.name ? 'Collapse skill' : 'Expand skill'}
            >
              {expanded === skill.name ? (
                <ChevronUp className="mr-1 h-3 w-3" />
              ) : (
                <ChevronDown className="mr-1 h-3 w-3" />
              )}
              {expanded === skill.name ? 'Hide' : 'View'}
            </Button>
            {skill.source === 'workspace' && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs text-destructive hover:text-destructive"
                onClick={() => handleRemove(skill.name)}
                disabled={removing === skill.name}
                aria-label={`Remove skill ${skill.name}`}
              >
                <Trash2 className="mr-1 h-3 w-3" />
                {removing === skill.name ? 'Removing...' : 'Remove'}
              </Button>
            )}
          </div>

          {expanded === skill.name && (
            <div className="mt-2 max-h-64 overflow-auto rounded-lg bg-muted/50 p-3">
              <pre className="whitespace-pre-wrap text-xs text-muted-foreground">
                {skillContent}
              </pre>
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}
