import type { ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { queryClient } from '../lib/query/queryClient'
import { AuthProvider } from '../features/auth/AuthProvider'
import { ToastProvider } from '../components/Toast'

/*
 * App-wide providers. Anything the whole tree needs is composed here and wraps
 * the router in main.tsx.
 *
 * Order matters in one place: AuthProvider sits *inside* ToastProvider, because
 * a session that expires while somebody is on a page should be able to say so
 * through a toast. And both sit inside QueryClientProvider, since every query
 * in the app is gated on the session settling.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>{children}</AuthProvider>
      </ToastProvider>
      {/* Dev-only panel for inspecting queries and the cache. Its corner button
          would sit on a phone nav-bar tab; index.css lifts it above the bar
          there. */}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
