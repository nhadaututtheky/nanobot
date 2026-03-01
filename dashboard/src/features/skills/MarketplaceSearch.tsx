import { useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Search, Download, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { rpc } from '@/ws/rpc'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import type { MarketplaceSkill } from '@/types/skills'

function useDebounce(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value)
  const timeoutRef = { current: undefined as ReturnType<typeof setTimeout> | undefined }

  // Simple inline debounce
  if (value !== debounced) {
    clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => setDebounced(value), delay)
  }

  return debounced
}

export function MarketplaceSearch() {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [installing, setInstalling] = useState<string | null>(null)
  const debouncedQuery = useDebounce(query, 500)

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['skills', 'search', debouncedQuery],
    queryFn: () => rpc.skills.search({ query: debouncedQuery, limit: 20 }),
    enabled: debouncedQuery.length >= 2,
  })

  const results: MarketplaceSkill[] = data?.results ?? []

  const handleInstall = useCallback(async (slug: string) => {
    setInstalling(slug)
    try {
      const res = await rpc.skills.marketplaceInstall({ slug })
      toast.success(`Installed: ${res.name}`)
      queryClient.invalidateQueries({ queryKey: ['skills', 'status'] })
    } catch (err) {
      toast.error(`Install failed: ${err instanceof Error ? err.message : 'unknown error'}`)
    } finally {
      setInstalling(null)
    }
  }, [queryClient])

  return (
    <div className="space-y-4">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search ClawHub marketplace (e.g. git, docker, api)..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="pl-10"
          aria-label="Search skills marketplace"
        />
        {isFetching && (
          <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
        )}
      </div>

      {isLoading && debouncedQuery.length >= 2 && (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 rounded-lg" />
          ))}
        </div>
      )}

      {!isLoading && debouncedQuery.length >= 2 && results.length === 0 && (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No results for &ldquo;{debouncedQuery}&rdquo;
        </p>
      )}

      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((skill) => (
            <Card key={skill.slug} className="flex items-center justify-between gap-4 p-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-medium">{skill.name}</p>
                  {skill.version && (
                    <Badge variant="outline" className="text-[10px]">v{skill.version}</Badge>
                  )}
                </div>
                <p className="truncate text-xs text-muted-foreground">{skill.description}</p>
                <div className="mt-1 flex items-center gap-3 text-[10px] text-muted-foreground">
                  {skill.slug && <span className="font-mono">{skill.slug}</span>}
                  {skill.downloads !== undefined && (
                    <span>{skill.downloads.toLocaleString()} downloads</span>
                  )}
                </div>
              </div>
              <Button
                size="sm"
                className="shrink-0"
                onClick={() => handleInstall(skill.slug)}
                disabled={installing === skill.slug}
                aria-label={`Install ${skill.name}`}
              >
                {installing === skill.slug ? (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                ) : (
                  <Download className="mr-1 h-3 w-3" />
                )}
                Install
              </Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
