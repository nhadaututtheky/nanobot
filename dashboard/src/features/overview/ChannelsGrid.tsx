import {
  MessageCircle,
  Gamepad2,
  Phone,
  Hash,
  Mail,
  Globe,
  Bell,
  MessageSquare,
  Bird,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { rpc } from '@/ws/rpc'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusDot } from '@/components/common/StatusDot'
import type { ReactNode } from 'react'

const channelIcons: Record<string, ReactNode> = {
  telegram: <MessageCircle className="h-4 w-4" />,
  discord: <Gamepad2 className="h-4 w-4" />,
  whatsapp: <Phone className="h-4 w-4" />,
  slack: <Hash className="h-4 w-4" />,
  email: <Mail className="h-4 w-4" />,
  feishu: <Bird className="h-4 w-4" />,
  dingtalk: <Bell className="h-4 w-4" />,
  qq: <MessageSquare className="h-4 w-4" />,
  matrix: <Globe className="h-4 w-4" />,
}

interface ChannelInfo {
  name: string
  enabled: boolean
  running: boolean
}

export function ChannelsGrid() {
  const { data, isLoading } = useQuery({
    queryKey: ['channels-status'],
    queryFn: () => rpc.channels.status(),
    refetchInterval: 30_000,
  })

  const channels = (data as ChannelInfo[] | undefined) ?? []

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Channels</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 rounded-lg" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (channels.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Channels</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No channels configured</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Channels</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {channels.map((ch) => (
            <div
              key={ch.name}
              className="flex items-center gap-2.5 rounded-lg border border-border p-3"
            >
              <div className="text-muted-foreground">
                {channelIcons[ch.name] ?? <Globe className="h-4 w-4" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm font-medium capitalize">{ch.name}</p>
              </div>
              {ch.enabled ? (
                <StatusDot status={ch.running ? 'online' : 'warning'} />
              ) : (
                <Badge variant="secondary" className="text-[10px]">Off</Badge>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
