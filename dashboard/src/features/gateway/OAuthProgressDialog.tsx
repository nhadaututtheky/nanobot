import { Loader2, ExternalLink, X } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import type { OAuthFlowState } from '@/types/gateway'

interface OAuthProgressDialogProps {
  flowState: OAuthFlowState
  onCancel: () => void
  onReopenUrl: () => void
}

export function OAuthProgressDialog({ flowState, onCancel, onReopenUrl }: OAuthProgressDialogProps) {
  const isOpen = flowState.phase === 'opening' || flowState.phase === 'polling'

  const providerName =
    isOpen || flowState.phase === 'error'
      ? 'provider' in flowState
        ? flowState.provider
        : ''
      : ''

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            Connecting to {providerName}
          </DialogTitle>
          <DialogDescription>
            A browser window has been opened for authentication. Complete the login there, then return here.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-center py-6">
          <div className="flex flex-col items-center gap-3">
            <div className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="h-2 w-2 rounded-full bg-primary animate-pulse"
                  style={{ animationDelay: `${i * 200}ms` }}
                />
              ))}
            </div>
            {flowState.phase === 'polling' && (
              <p className="text-sm text-muted-foreground">
                Waiting for authentication... ({Math.round(flowState.attempts * 2)}s)
              </p>
            )}
            {flowState.phase === 'opening' && (
              <p className="text-sm text-muted-foreground">Opening browser...</p>
            )}
          </div>
        </div>

        <DialogFooter className="flex-row gap-2 sm:justify-between">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            <X className="mr-1 h-3 w-3" />
            Cancel
          </Button>
          {flowState.phase === 'polling' && (
            <Button variant="outline" size="sm" onClick={onReopenUrl}>
              <ExternalLink className="mr-1 h-3 w-3" />
              Open Again
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
