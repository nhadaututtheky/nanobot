import { useQuery } from '@tanstack/react-query'
import { Coins } from 'lucide-react'
import { rpc } from '@/ws/rpc'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { formatCompact } from '@/lib/utils'

interface TokenUsageBadgeProps {
  sessionKey: string
}

interface UsageData {
  totalTokens?: number
  inputTokens?: number
  outputTokens?: number
}

export function TokenUsageBadge({ sessionKey }: TokenUsageBadgeProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['sessions', 'usage', sessionKey],
    queryFn: () => rpc.sessions.usage({ sessionKey }),
    enabled: Boolean(sessionKey),
  })

  if (isLoading) {
    return <Skeleton className="h-5 w-16 rounded-full" />
  }

  const usage = data as UsageData | undefined
  const total = usage?.totalTokens

  if (total === undefined) return null

  return (
    <Badge variant="outline" className="gap-1 font-mono text-xs">
      <Coins className="h-3 w-3" aria-hidden="true" />
      {formatCompact(total)} tokens
    </Badge>
  )
}
