import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { rpc } from '@/ws/rpc'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

const schema = z.object({
  expression: z.string().min(1, 'Schedule expression is required').refine(
    (val) => val.split(' ').length >= 5 || val.startsWith('@'),
    'Must be a valid cron expression (e.g. "0 9 * * *") or macro (e.g. "@daily")',
  ),
  task: z.string().min(1, 'Message / task is required'),
  sessionKey: z.string().optional(),
  enabled: z.boolean(),
})

type FormValues = z.infer<typeof schema>

// ---------------------------------------------------------------------------
// CronJobForm
// ---------------------------------------------------------------------------

interface CronJobFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CronJobForm({ open, onOpenChange }: CronJobFormProps) {
  const queryClient = useQueryClient()

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      expression: '',
      task: '',
      sessionKey: '',
      enabled: true,
    },
  })

  const addMutation = useMutation({
    mutationFn: (values: FormValues) =>
      rpc.cron.add({
        expression: values.expression,
        task: values.task,
        sessionKey: values.sessionKey || undefined,
        enabled: values.enabled,
      }),
    onSuccess: () => {
      toast.success('Cron job added')
      void queryClient.invalidateQueries({ queryKey: ['cron-list'] })
      form.reset()
      onOpenChange(false)
    },
    onError: (err: unknown) => {
      toast.error('Failed to add job', {
        description: err instanceof Error ? err.message : 'Unknown error',
      })
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Cron Job</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((v) => addMutation.mutate(v))}
            className="space-y-4"
          >
            <FormField
              control={form.control}
              name="expression"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Schedule Expression</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="0 9 * * * or @daily"
                      className="font-mono text-sm"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="task"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Message / Task</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="What should the agent do?"
                      className="min-h-[80px] resize-none text-sm"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="sessionKey"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Session Key (optional)</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Leave blank for default session"
                      className="font-mono text-sm"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="enabled"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                  <FormLabel className="cursor-pointer">Enabled</FormLabel>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={addMutation.isPending}>
                {addMutation.isPending && (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                )}
                Add Job
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
