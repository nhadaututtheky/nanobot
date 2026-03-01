import { cn } from '@/lib/utils'
import { formatRelativeTime } from '@/lib/utils'

interface ChatBubbleProps {
  role: 'user' | 'assistant' | 'context' | 'system'
  content: string
  timestamp?: string | Date
  className?: string
}

function hasCodeBlock(text: string): boolean {
  return text.includes('```')
}

function renderContent(content: string) {
  if (!hasCodeBlock(content)) {
    return <p className="whitespace-pre-wrap text-sm leading-relaxed">{content}</p>
  }

  const parts = content.split(/(```[\s\S]*?```)/g)
  return (
    <div className="space-y-2">
      {parts.map((part, i) => {
        if (part.startsWith('```') && part.endsWith('```')) {
          const lines = part.slice(3, -3).split('\n')
          const lang = lines[0]
          const code = lines.slice(1).join('\n').trimEnd()
          return (
            <pre
              key={i}
              className="overflow-x-auto rounded-md bg-muted px-3 py-2 font-mono text-xs leading-relaxed"
            >
              {lang && (
                <span className="mb-1 block text-xs text-muted-foreground">{lang}</span>
              )}
              <code>{code}</code>
            </pre>
          )
        }
        return part ? (
          <p key={i} className="whitespace-pre-wrap text-sm leading-relaxed">
            {part}
          </p>
        ) : null
      })}
    </div>
  )
}

export function ChatBubble({ role, content, timestamp, className }: ChatBubbleProps) {
  const isUser = role === 'user'
  const isAssistant = role === 'assistant'
  const isContext = role === 'context' || role === 'system'

  if (isContext) {
    return (
      <div className={cn('flex justify-center', className)}>
        <div className="max-w-md rounded-md bg-muted/50 px-3 py-1.5 text-center">
          <p className="text-xs text-muted-foreground">{content}</p>
          {timestamp && (
            <span className="text-xs text-muted-foreground/60">
              {formatRelativeTime(timestamp)}
            </span>
          )}
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'flex gap-2',
        isUser ? 'flex-row-reverse' : 'flex-row',
        className,
      )}
    >
      <div
        className={cn(
          'max-w-[75%] rounded-xl px-4 py-3 shadow-sm',
          isUser && 'bg-primary/10 text-foreground rounded-tr-sm',
          isAssistant && 'bg-card border border-border rounded-tl-sm',
        )}
      >
        <div className="mb-1 flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground capitalize">
            {role}
          </span>
          {timestamp && (
            <span className="text-xs text-muted-foreground/60">
              {formatRelativeTime(timestamp)}
            </span>
          )}
        </div>
        {renderContent(content)}
      </div>
    </div>
  )
}
