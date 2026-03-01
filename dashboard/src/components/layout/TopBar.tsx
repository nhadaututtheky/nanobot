import { Bot, Moon, Sun, Menu } from 'lucide-react'
import { useThemeStore } from '@/stores/useThemeStore'
import { useConnectionStore } from '@/stores/useConnectionStore'
import { Button } from '@/components/ui/button'
import { StatusDot } from '@/components/common/StatusDot'
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet'
import { MobileNav } from './MobileNav'

export function TopBar() {
  const theme = useThemeStore((s) => s.theme)
  const toggleTheme = useThemeStore((s) => s.toggleTheme)
  const wsState = useConnectionStore((s) => s.state)

  return (
    <header className="flex h-12 items-center justify-between border-b border-border bg-card px-4">
      <div className="flex items-center gap-3">
        {/* Mobile menu */}
        <Sheet>
          <SheetTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-64 p-0">
            <MobileNav />
          </SheetContent>
        </Sheet>

        <Bot className="h-6 w-6 text-primary" />
        <h1 className="font-heading text-lg font-bold">NanoBot</h1>

        <StatusDot
          status={
            wsState === 'connected'
              ? 'online'
              : wsState === 'failed'
                ? 'error'
                : 'warning'
          }
          label={wsState}
        />
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          {theme === 'dark' ? (
            <Sun className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </Button>
      </div>
    </header>
  )
}
