import type { ReactNode } from 'react'
import { Bot, Cpu, Sparkles, Zap, Brain, Cloud, Github, Loader2, ExternalLink, Unplug } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { StatusDot } from '@/components/common/StatusDot'
import { OAUTH_SUPPORTED } from '@/hooks/useGatewayAuth'
import type { ProviderAuthState, OAuthFlowState, GatewayProvider } from '@/types/gateway'

const PROVIDER_ICONS: Record<GatewayProvider, ReactNode> = {
  anthropic: <Bot className="h-5 w-5" />,
  codex: <Cpu className="h-5 w-5" />,
  gemini: <Sparkles className="h-5 w-5" />,
  iflow: <Zap className="h-5 w-5" />,
  qwen: <Brain className="h-5 w-5" />,
  kiro: <Cloud className="h-5 w-5" />,
  copilot: <Github className="h-5 w-5" />,
}

const TIER_STYLES: Record<string, string> = {
  subscription: 'border-primary/30 text-primary',
  cheap: 'border-warning/30 text-warning',
  free: 'border-success/30 text-success',
}

interface ProviderCardProps {
  state: ProviderAuthState
  oauthFlow: OAuthFlowState
  onConnect: (provider: GatewayProvider) => void
  onDisconnect: (name: string) => void
  isDisconnecting: boolean
  gatewayReachable: boolean
}

export function ProviderCard({
  state,
  oauthFlow,
  onConnect,
  onDisconnect,
  isDisconnecting,
  gatewayReachable,
}: ProviderCardProps) {
  const isOAuthActive =
    oauthFlow.phase !== 'idle' &&
    oauthFlow.phase !== 'success' &&
    'provider' in oauthFlow &&
    oauthFlow.provider === state.provider

  const isAnyOAuthActive = oauthFlow.phase !== 'idle'
  const supportsOAuth = OAUTH_SUPPORTED.includes(state.provider)

  const isErrorForThis =
    oauthFlow.phase === 'error' &&
    'provider' in oauthFlow &&
    oauthFlow.provider === state.provider

  return (
    <Card className="relative overflow-hidden hover:border-primary/30 transition-colors">
      <CardContent className="flex items-start gap-4 p-5">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-muted/50 text-muted-foreground">
          {PROVIDER_ICONS[state.provider]}
        </div>

        <div className="flex-1 min-w-0 space-y-2">
          <div className="flex items-center gap-2">
            <span className="font-semibold truncate">{state.meta.label}</span>
            <Badge variant="outline" className={`text-[10px] ${TIER_STYLES[state.meta.tier] ?? ''}`}>
              {state.meta.tier}
            </Badge>
            <Badge variant="secondary" className="font-mono text-[10px]">
              {state.meta.prefix}
            </Badge>
          </div>

          <p className="text-sm text-muted-foreground line-clamp-1">
            {state.meta.description}
          </p>

          <div className="flex items-center gap-2 pt-0.5">
            {state.connected ? (
              <>
                <StatusDot status="online" />
                <span className="text-xs text-success truncate">
                  {state.authFile?.email ?? state.authFile?.label ?? 'Connected'}
                  {(state.connectedCount ?? 0) > 1 && (
                    <span className="text-muted-foreground ml-1">+{(state.connectedCount ?? 1) - 1}</span>
                  )}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto h-7 text-xs text-muted-foreground hover:text-destructive"
                  onClick={() => state.authFile && onDisconnect(state.authFile.name)}
                  disabled={isDisconnecting}
                >
                  <Unplug className="mr-1 h-3 w-3" />
                  Disconnect
                </Button>
              </>
            ) : isOAuthActive ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin text-primary" />
                <span className="text-xs text-primary">
                  Waiting for auth...
                  {oauthFlow.phase === 'polling' && (
                    <span className="text-muted-foreground ml-1">
                      ({oauthFlow.attempts}s)
                    </span>
                  )}
                </span>
              </>
            ) : isErrorForThis ? (
              <>
                <StatusDot status="offline" />
                <span className="text-xs text-destructive truncate">
                  {oauthFlow.phase === 'error' && oauthFlow.message}
                </span>
              </>
            ) : (
              <>
                <StatusDot status="offline" />
                <span className="text-xs text-muted-foreground">Not connected</span>
                {supportsOAuth ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="ml-auto h-7 text-xs"
                    onClick={() => onConnect(state.provider)}
                    disabled={!gatewayReachable || isAnyOAuthActive}
                  >
                    <ExternalLink className="mr-1 h-3 w-3" />
                    Connect
                  </Button>
                ) : (
                  <span className="ml-auto text-[10px] text-muted-foreground">Manual setup</span>
                )}
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
