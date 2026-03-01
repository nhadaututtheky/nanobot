import { useRef, type KeyboardEvent } from 'react'
import { Send, Square } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { rpc } from '@/ws/rpc'
import { useChatStore } from '@/stores/useChatStore'

interface ChatInputProps {
  sessionKey: string | null
  className?: string
}

export function ChatInput({ sessionKey, className }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const activeRunId = useChatStore((s) => s.activeRunId)

  const disabled = !sessionKey

  async function handleSend() {
    const textarea = textareaRef.current
    if (!textarea || !sessionKey) return

    const message = textarea.value.trim()
    if (!message) return

    textarea.value = ''
    textarea.style.height = 'auto'

    try {
      await rpc.chat.send({ sessionKey, content: message })
    } catch (err) {
      toast.error('Failed to send message', {
        description: err instanceof Error ? err.message : 'Unknown error',
      })
    }
  }

  async function handleAbort() {
    if (!sessionKey || !activeRunId) return
    try {
      await rpc.chat.abort({ sessionKey })
    } catch (err) {
      toast.error('Failed to abort', {
        description: err instanceof Error ? err.message : 'Unknown error',
      })
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!isStreaming) {
        void handleSend()
      }
    }
  }

  function handleInput() {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`
  }

  return (
    <div className={cn('flex items-end gap-2 border-t bg-background p-3', className)}>
      <Textarea
        ref={textareaRef}
        placeholder={disabled ? 'Select a session to start chatting' : 'Type a message…'}
        disabled={disabled || isStreaming}
        rows={1}
        className="min-h-[40px] resize-none overflow-hidden"
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        aria-label="Chat message input"
      />
      {isStreaming ? (
        <Button
          size="icon"
          variant="destructive"
          onClick={() => void handleAbort()}
          aria-label="Stop generation"
          className="shrink-0"
        >
          <Square className="h-4 w-4" />
        </Button>
      ) : (
        <Button
          size="icon"
          onClick={() => void handleSend()}
          disabled={disabled}
          aria-label="Send message"
          className="shrink-0"
        >
          <Send className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}
