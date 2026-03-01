import { useState, useMemo } from 'react'
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { rpc } from '@/ws/rpc'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { formatCompact, formatRelativeTime } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SessionUsage {
  sessionKey: string
  tokens: number
  turns: number
  lastActive: string
}

type SortKey = 'tokens' | 'turns' | 'lastActive'
type SortDir = 'asc' | 'desc'

interface SessionUsageTableProps {
  onSessionSelect?: (sessionKey: string) => void
}

// ---------------------------------------------------------------------------
// SessionUsageTable
// ---------------------------------------------------------------------------

export function SessionUsageTable({ onSessionSelect }: SessionUsageTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('tokens')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { data, isLoading } = useQuery({
    queryKey: ['sessions-usage-all'],
    queryFn: async () => {
      const sessions = await rpc.sessions.list()
      const list = sessions as Array<{ sessionKey: string }>
      const usages = await Promise.all(
        list.map((s) =>
          rpc.sessions.usage({ sessionKey: s.sessionKey }).catch(() => null),
        ),
      )
      return list
        .map((s, i) => {
          const u = usages[i] as Record<string, unknown> | null
          return {
            sessionKey: s.sessionKey,
            tokens: (u?.['totalTokens'] as number) ?? 0,
            turns: (u?.['turns'] as number) ?? 0,
            lastActive: (u?.['lastActive'] as string) ?? '',
          } satisfies SessionUsage
        })
        .filter((s) => s.tokens > 0)
    },
    refetchInterval: 60_000,
  })

  const sorted = useMemo(() => {
    if (!data) return []
    return [...data].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av
      }
      if (typeof av === 'string' && typeof bv === 'string') {
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
      }
      return 0
    })
  }, [data, sortKey, sortDir])

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <ArrowUpDown className="ml-1 h-3 w-3 opacity-40" />
    return sortDir === 'asc'
      ? <ArrowUp className="ml-1 h-3 w-3" />
      : <ArrowDown className="ml-1 h-3 w-3" />
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Session Usage</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <div className="space-y-2 px-4 pb-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : !sorted.length ? (
          <p className="px-4 pb-6 pt-2 text-center text-sm text-muted-foreground">
            No session data available
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30 text-xs text-muted-foreground">
                  <th className="px-4 py-2 text-left font-medium">Session</th>
                  <th className="px-4 py-2 text-right font-medium">
                    <button
                      type="button"
                      className="flex items-center ml-auto cursor-pointer hover:text-foreground"
                      onClick={() => handleSort('tokens')}
                    >
                      Tokens <SortIcon col="tokens" />
                    </button>
                  </th>
                  <th className="px-4 py-2 text-right font-medium">
                    <button
                      type="button"
                      className="flex items-center ml-auto cursor-pointer hover:text-foreground"
                      onClick={() => handleSort('turns')}
                    >
                      Turns <SortIcon col="turns" />
                    </button>
                  </th>
                  <th className="px-4 py-2 text-right font-medium">
                    <button
                      type="button"
                      className="flex items-center ml-auto cursor-pointer hover:text-foreground"
                      onClick={() => handleSort('lastActive')}
                    >
                      Last Active <SortIcon col="lastActive" />
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {sorted.map((row) => (
                  <tr
                    key={row.sessionKey}
                    className="hover:bg-muted/20 transition-colors cursor-pointer"
                    onClick={() => onSessionSelect?.(row.sessionKey)}
                  >
                    <td className="px-4 py-2.5 font-mono text-xs truncate max-w-[200px]">
                      {row.sessionKey}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs font-bold">
                      {formatCompact(row.tokens)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">
                      {row.turns}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-muted-foreground">
                      {row.lastActive ? formatRelativeTime(row.lastActive) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
