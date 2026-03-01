import { useQuery } from '@tanstack/react-query'
import { DollarSign } from 'lucide-react'
import { rpc } from '@/ws/rpc'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { formatCompact } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ModelCost {
  model: string
  tokens: number
  cost: number
}

interface CostData {
  totalCost: number
  totalTokens: number
  currency: string
  byModel: ModelCost[]
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

function formatCurrency(value: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }).format(value)
}

// ---------------------------------------------------------------------------
// CostBreakdown
// ---------------------------------------------------------------------------

export function CostBreakdown() {
  const { data, isLoading } = useQuery({
    queryKey: ['usage-cost-detail'],
    queryFn: () => rpc.system.usageCost(),
    select: (d) => {
      const raw = d as Record<string, unknown>
      const byModelRaw = raw.byModel as Record<string, number> | ModelCost[] | undefined
      const byModel: ModelCost[] = Array.isArray(byModelRaw)
        ? byModelRaw
        : Object.entries(byModelRaw ?? {}).map(([model, cost]) => ({
            model,
            tokens: 0,
            cost: typeof cost === 'number' ? cost : 0,
          }))
      return {
        totalCost: (raw.totalCost as number) ?? 0,
        totalTokens: (raw.totalTokens as number) ?? 0,
        currency: (raw.currency as string) ?? 'USD',
        byModel,
      } satisfies CostData
    },
    refetchInterval: 60_000,
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <DollarSign className="h-4 w-4" />
          Cost Breakdown
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-10 w-32" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
          </div>
        ) : (
          <>
            {/* Big number */}
            <div>
              <p className="text-3xl font-mono font-bold tracking-tight">
                {data ? formatCurrency(data.totalCost, data.currency) : '—'}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {data?.totalTokens ? `${formatCompact(data.totalTokens)} tokens total` : 'No data'}
              </p>
            </div>

            {/* By model table */}
            {data?.byModel && data.byModel.length > 0 && (
              <div className="divide-y divide-border overflow-hidden rounded-md border border-border text-sm">
                <div className="grid grid-cols-3 bg-muted/30 px-3 py-1.5 text-xs font-medium text-muted-foreground">
                  <span>Model</span>
                  <span className="text-right">Tokens</span>
                  <span className="text-right">Cost</span>
                </div>
                {data.byModel.map((row) => (
                  <div key={row.model} className="grid grid-cols-3 px-3 py-2 hover:bg-muted/20">
                    <span className="truncate font-mono text-xs">{row.model}</span>
                    <span className="text-right font-mono text-xs text-muted-foreground">
                      {formatCompact(row.tokens)}
                    </span>
                    <span className="text-right font-mono text-xs">
                      {formatCurrency(row.cost, data.currency)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
