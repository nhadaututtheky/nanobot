import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  MessageSquare,
  Settings,
  Clock,
  BarChart3,
  Bot,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { path: '/', label: 'Overview', icon: LayoutDashboard },
  { path: '/chat', label: 'Chat', icon: MessageSquare },
  { path: '/config', label: 'Config', icon: Settings },
  { path: '/cron', label: 'Cron', icon: Clock },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
]

export function MobileNav() {
  return (
    <div className="flex h-full flex-col bg-card">
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <Bot className="h-6 w-6 text-primary" />
        <span className="font-heading text-lg font-bold">NanoBot</span>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-2 pt-4">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                'hover:bg-accent/10',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground',
              )
            }
          >
            <item.icon className="h-5 w-5" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
