import { useState } from 'react'
import { Copy, Check, WrapText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

interface ConfigRawViewProps {
  value: string
  onChange: (value: string) => void
}

export function ConfigRawView({ value, onChange }: ConfigRawViewProps) {
  const [copied, setCopied] = useState(false)

  function handleFormat() {
    try {
      const parsed: unknown = JSON.parse(value)
      onChange(JSON.stringify(parsed, null, 2))
    } catch {
      // invalid JSON — leave as-is
    }
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(value)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" size="sm" onClick={handleFormat}>
          <WrapText className="mr-1.5 h-3.5 w-3.5" />
          Format
        </Button>
        <Button variant="outline" size="sm" onClick={handleCopy}>
          {copied ? (
            <Check className="mr-1.5 h-3.5 w-3.5 text-success" />
          ) : (
            <Copy className="mr-1.5 h-3.5 w-3.5" />
          )}
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          'min-h-[480px] font-mono text-xs leading-relaxed',
          'resize-y rounded-md border-border bg-muted/30',
        )}
        spellCheck={false}
        aria-label="Raw JSON configuration"
      />
    </div>
  )
}
