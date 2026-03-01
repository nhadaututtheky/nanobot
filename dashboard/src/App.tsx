import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { WebSocketProvider } from '@/ws/provider'
import { AppShell } from '@/components/layout/AppShell'
import { PageSkeleton } from '@/components/common/PageSkeleton'

// Lazy load pages — each becomes its own chunk
const OverviewPage = lazy(() => import('@/features/overview/OverviewPage').then(m => ({ default: m.OverviewPage })))
const ChatPage = lazy(() => import('@/features/chat/ChatPage').then(m => ({ default: m.ChatPage })))
const ConfigPage = lazy(() => import('@/features/config/ConfigPage').then(m => ({ default: m.ConfigPage })))
const CronPage = lazy(() => import('@/features/cron/CronPage').then(m => ({ default: m.CronPage })))
const GatewayPage = lazy(() => import('@/features/gateway/GatewayPage').then(m => ({ default: m.GatewayPage })))
const AnalyticsPage = lazy(() => import('@/features/analytics/AnalyticsPage').then(m => ({ default: m.AnalyticsPage })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: (failureCount, error) => {
        if (error instanceof Error && error.message.includes('AUTH')) return false
        return failureCount < 2
      },
    },
  },
})

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>
        <BrowserRouter>
          <AppShell>
            <Suspense fallback={<PageSkeleton />}>
              <Routes>
                <Route path="/" element={<OverviewPage />} />
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/chat/:sessionKey" element={<ChatPage />} />
                <Route path="/config" element={<ConfigPage />} />
                <Route path="/providers" element={<GatewayPage />} />
                <Route path="/cron" element={<CronPage />} />
                <Route path="/analytics" element={<AnalyticsPage />} />
              </Routes>
            </Suspense>
          </AppShell>
        </BrowserRouter>
        <Toaster
          position="bottom-right"
          toastOptions={{
            className: 'bg-card text-card-foreground border-border',
          }}
        />
      </WebSocketProvider>
    </QueryClientProvider>
  )
}
