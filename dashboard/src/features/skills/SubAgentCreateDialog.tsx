import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  THINKING_STYLE_OPTIONS,
  PERSISTENCE_OPTIONS,
  RESPONSE_LENGTH_OPTIONS,
} from './SubAgentPresets'
import type { SubAgentRoleConfig } from '@/types/skills'

interface SubAgentCreateDialogProps {
  existingRoles: string[]
  onCreateRole: (roleId: string, config: SubAgentRoleConfig) => void
}

const EMPTY_ROLE: SubAgentRoleConfig = {
  model: '',
  maxIterations: 0,
  temperature: 0,
  maxTokens: 0,
  tools: [],
  displayName: '',
  description: '',
  persona: '',
  icon: '🤖',
  strengths: [],
  builtin: false,
  thinkingStyle: 'balanced',
  persistence: 'normal',
  responseLength: 'normal',
}

export function SubAgentCreateDialog({
  existingRoles,
  onCreateRole,
}: SubAgentCreateDialogProps) {
  const [open, setOpen] = useState(false)
  const [roleId, setRoleId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [icon, setIcon] = useState('🤖')
  const [description, setDescription] = useState('')
  const [persona, setPersona] = useState('')
  const [thinkingStyle, setThinkingStyle] = useState('balanced')
  const [persistence, setPersistence] = useState('normal')
  const [responseLength, setResponseLength] = useState('normal')
  const [cloneFrom, setCloneFrom] = useState('')

  function reset() {
    setRoleId('')
    setDisplayName('')
    setIcon('🤖')
    setDescription('')
    setPersona('')
    setThinkingStyle('balanced')
    setPersistence('normal')
    setResponseLength('normal')
    setCloneFrom('')
  }

  function handleCreate() {
    const slug = roleId
      .toLowerCase()
      .replace(/[^a-z0-9_-]/g, '_')
      .replace(/_{2,}/g, '_')
      .replace(/^_|_$/g, '')

    if (!slug || existingRoles.includes(slug)) return

    const config: SubAgentRoleConfig = {
      ...EMPTY_ROLE,
      displayName,
      icon,
      description,
      persona,
      thinkingStyle,
      persistence,
      responseLength,
    }

    onCreateRole(slug, config)
    reset()
    setOpen(false)
  }

  const slugValid =
    roleId.trim().length > 0 &&
    !existingRoles.includes(
      roleId
        .toLowerCase()
        .replace(/[^a-z0-9_-]/g, '_')
        .replace(/_{2,}/g, '_')
        .replace(/^_|_$/g, ''),
    )

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <Plus className="h-3.5 w-3.5" />
          Add Sub-Agent
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Create Custom Sub-Agent</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Clone From */}
          {existingRoles.length > 0 && (
            <div className="space-y-1">
              <Label className="text-xs">Clone from (optional)</Label>
              <Select value={cloneFrom} onValueChange={setCloneFrom}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="Start from scratch" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Start from scratch</SelectItem>
                  {existingRoles.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Role ID */}
          <div className="space-y-1">
            <Label className="text-xs">
              Role ID <span className="text-destructive">*</span>
            </Label>
            <Input
              placeholder="e.g. debugger, translator, data-analyst"
              value={roleId}
              onChange={(e) => setRoleId(e.target.value)}
              className="h-8 text-xs"
            />
            {roleId && !slugValid && (
              <p className="text-[10px] text-destructive">
                Role ID already exists or is empty
              </p>
            )}
          </div>

          {/* Display Name + Icon */}
          <div className="grid grid-cols-[1fr_60px] gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Display Name</Label>
              <Input
                placeholder="e.g. Bug Hunter"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Icon</Label>
              <Input
                value={icon}
                onChange={(e) => setIcon(e.target.value)}
                className="h-8 text-center text-sm"
                maxLength={2}
              />
            </div>
          </div>

          {/* Description */}
          <div className="space-y-1">
            <Label className="text-xs">Description</Label>
            <Input
              placeholder="What does this agent do?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="h-8 text-xs"
            />
          </div>

          {/* Presets */}
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label className="text-[10px]">Thinking</Label>
              <Select value={thinkingStyle} onValueChange={setThinkingStyle}>
                <SelectTrigger className="h-7 text-[11px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {THINKING_STYLE_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-[10px]">Persistence</Label>
              <Select value={persistence} onValueChange={setPersistence}>
                <SelectTrigger className="h-7 text-[11px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PERSISTENCE_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-[10px]">Response</Label>
              <Select value={responseLength} onValueChange={setResponseLength}>
                <SelectTrigger className="h-7 text-[11px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RESPONSE_LENGTH_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Persona */}
          <div className="space-y-1">
            <Label className="text-xs">Persona (optional)</Label>
            <Textarea
              placeholder="Personality, tone, behavior instructions..."
              value={persona}
              onChange={(e) => setPersona(e.target.value)}
              className="min-h-[60px] text-xs"
            />
          </div>

          {/* Create */}
          <Button
            className="w-full"
            disabled={!slugValid}
            onClick={handleCreate}
          >
            Create Sub-Agent
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
