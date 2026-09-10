import { AlertTriangle, Inbox } from 'lucide-react'
import { Card } from './Card'
import { SkeletonCards, SkeletonRows } from './Skeleton'
import { ApiError } from '../lib/api/errors'

/*
 * Shared loading / error / empty states, so every browse screen renders the
 * same way and the four-state pattern is written once rather than per page.
 */

/**
 * Loading. Defaults to a lightweight inline line, which is safe in any layout;
 * pass a `variant` on a browse screen for a skeleton that holds the page's
 * shape while data arrives, so the content doesn't jump into place under a
 * thumb that has already started moving.
 */
export function Loading({
  label = 'Loading…',
  variant = 'text',
}: {
  label?: string
  variant?: 'cards' | 'rows' | 'text'
}) {
  if (variant === 'cards') return <SkeletonCards />
  if (variant === 'rows') return <SkeletonRows />
  return (
    <p className="text-ash motion-safe:animate-pulse" aria-busy="true">
      {label}
    </p>
  )
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof ApiError ? error.message : 'Something went wrong.'
  return (
    <Card border="border-wrong/40" className="flex items-center gap-3 p-6">
      <AlertTriangle className="shrink-0 text-wrong" size={20} />
      <p className="text-wrong">{message}</p>
    </Card>
  )
}

export function EmptyState({ message, action }: { message: string; action?: React.ReactNode }) {
  return (
    <Card className="flex flex-col items-center gap-4 p-10 text-center">
      <Inbox className="text-ash/60" size={28} />
      <p className="text-ash">{message}</p>
      {action}
    </Card>
  )
}
