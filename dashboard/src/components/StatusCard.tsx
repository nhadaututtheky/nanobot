import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

interface StatusCardProps {
  icon: ReactNode
  label: string
  value: string | number
  subtext?: string
  loading?: boolean
  className?: string
}

export function StatusCard({ icon, label, value, subtext, loading, className }: StatusCardProps) {
  if (loading) {
    return (
      <Card className={cn('p-4', className)}>
        <CardContent className="flex items-center gap-3 p-0">
          <Skeleton className="h-10 w-10 rounded-lg" />
          <div className="space-y-1.5">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-6 w-20" />
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={cn('p-4 transition-shadow hover:shadow-md', className)}>
      <CardContent className="flex items-center gap-3 p-0">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          {icon}
        </div>
        <div>
          <p className="font-label text-muted-foreground">{label}</p>
          <p className="font-mono-bold text-xl">{value}</p>
          {subtext && (
            <p className="text-xs text-muted-foreground">{subtext}</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
