import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { rpc } from '@/ws/rpc'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { TrendingUp } from 'lucide-react'
import { formatCompact } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TimeseriesPoint {
  date: string
  tokens: number
  inputTokens?: number
  outputTokens?: number
}

interface UsageTimeseriesProps {
  sessionKeys: string[]
}

// ---------------------------------------------------------------------------
// UsageTimeseries
// ---------------------------------------------------------------------------

export function UsageTimeseries({ sessionKeys }: UsageTimeseriesProps) {
  const [selectedSession, setSelectedSession] = useState<string>(sessionKeys[0] ?? '')
  const [period, setPeriod] = useState('7d')

  const { data, isLoading } = useQuery({
    queryKey: ['usage-timeseries', selectedSession, period],
    queryFn: () =>
      rpc.sessions.usageTimeseries({
        sessionKey: selectedSession,
        period,
        granularity: 'day',
      }),
    enabled: !!selectedSession,
    select: (d) => {
      const raw = d as { points?: TimeseriesPoint[] } | TimeseriesPoint[]
      return Array.isArray(raw) ? raw : (raw.points ?? [])
    },
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <CardTitle className="flex items-center gap-2 text-base">
            <TrendingUp className="h-4 w-4" />
            Token Usage
          </CardTitle>
          <div className="flex items-center gap-2">
            <Select
              value={period}
              onValueChange={setPeriod}
            >
              <SelectTrigger className="h-8 w-24 text-xs" aria-label="Select period">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="24h">24h</SelectItem>
                <SelectItem value="7d">7 days</SelectItem>
                <SelectItem value="30d">30 days</SelectItem>
              </SelectContent>
            </Select>
            {sessionKeys.length > 0 && (
              <Select
                value={selectedSession}
                onValueChange={setSelectedSession}
              >
                <SelectTrigger className="h-8 w-40 text-xs" aria-label="Select session">
                  <SelectValue placeholder="Select session" />
                </SelectTrigger>
                <SelectContent>
                  {[...new Set(sessionKeys)].map((k) => (
                    <SelectItem key={k} value={k}>
                      <span className="font-mono text-xs">{k}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : !data || data.length === 0 ? (
          <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
            No timeseries data for this session
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="tokensGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--chart-1)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--border)"
                vertical={false}
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tickFormatter={(v: number) => formatCompact(v)}
                tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--card)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  fontSize: 12,
                  color: 'var(--card-foreground)',
                }}
                formatter={(value: number | undefined) => [formatCompact(value ?? 0), 'Tokens']}
              />
              <Area
                type="monotone"
                dataKey="tokens"
                stroke="var(--chart-1)"
                strokeWidth={2}
                fill="url(#tokensGradient)"
                dot={false}
                activeDot={{ r: 4 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}
