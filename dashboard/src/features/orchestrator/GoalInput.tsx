import { useState } from 'react'
import { Play, Eye, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface GoalInputProps {
  onRun: (goal: string, context: string) => void
  onDecompose: (goal: string, context: string) => void
  isRunning: boolean
  isDecomposing: boolean
}

const MAX_GOAL_LENGTH = 2000

export function GoalInput({ onRun, onDecompose, isRunning, isDecomposing }: GoalInputProps) {
  const [goal, setGoal] = useState('')
  const [context, setContext] = useState('')
  const [showContext, setShowContext] = useState(false)

  const canSubmit = goal.trim().length > 0 && !isRunning && !isDecomposing

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="space-y-1">
        <label htmlFor="orchestrator-goal" className="sr-only">Goal</label>
        <Textarea
          id="orchestrator-goal"
          placeholder="Describe your goal... (e.g., 'Research React state libs, build comparison, write blog post')"
          value={goal}
          onChange={(e) => setGoal(e.target.value.slice(0, MAX_GOAL_LENGTH))}
          maxLength={MAX_GOAL_LENGTH}
          className="min-h-[80px] resize-none bg-background"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && canSubmit) {
              onRun(goal.trim(), context.trim())
            }
          }}
        />
        {goal.length > MAX_GOAL_LENGTH * 0.8 && (
          <p className="text-[10px] text-muted-foreground text-right">
            {goal.length}/{MAX_GOAL_LENGTH}
          </p>
        )}
      </div>

      {showContext && (
        <div>
          <label htmlFor="orchestrator-context" className="sr-only">Additional context</label>
          <Textarea
            id="orchestrator-context"
            placeholder="Additional context (optional)..."
            value={context}
            onChange={(e) => setContext(e.target.value)}
            className="min-h-[60px] resize-none bg-background text-sm"
          />
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowContext(!showContext)}
          className="text-xs text-muted-foreground"
        >
          {showContext ? 'Hide context' : '+ Add context'}
        </Button>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onDecompose(goal.trim(), context.trim())}
            disabled={!canSubmit}
          >
            {isDecomposing ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <Eye className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            )}
            Preview
          </Button>

          <Button
            size="sm"
            onClick={() => onRun(goal.trim(), context.trim())}
            disabled={!canSubmit}
          >
            {isRunning ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <Play className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            )}
            Run
          </Button>
        </div>
      </div>
    </div>
  )
}
