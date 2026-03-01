import { cn } from '@/lib/utils'

interface StatusDotProps {
  status: 'online' | 'warning' | 'error' | 'offline'
  label?: string
  className?: string
}

const dotColors = {
  online: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-destructive',
  offline: 'bg-muted-foreground',
} as const

export function StatusDot({ status, label, className }: StatusDotProps) {
  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      <span className={cn('h-2 w-2 rounded-full', dotColors[status])} />
      {label && (
        <span className="text-xs text-muted-foreground capitalize">
          {label}
        </span>
      )}
    </div>
  )
}
