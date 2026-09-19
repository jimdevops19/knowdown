import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

/*
 * The chrome shared by the app's *standing* prompts — "install knowdown", "a
 * new version is ready".
 *
 * These are not toasts, and the difference is the whole reason this exists
 * alongside <Toast />: a toast is something that happened and expires on its
 * own, a prompt is a question waiting for an answer and stays until it gets
 * one. There is at most a handful of them, ever.
 *
 * Where they sit is the other half. The naive `bottom: 0` lands on the phone
 * tab bar and under the iOS home indicator, so the stack sits on top of the
 * bar instead — `--nav-bar-inset` is the bar's height plus the home indicator,
 * already stated once in index.css, and half a rem of air above it.
 *
 * It used to hang from `top: 65dvh`, which put a fixed, full-width bar two
 * thirds of the way down an otherwise empty screen. Nothing else in the app
 * floats there, so it didn't read as a prompt about the app — it read as the
 * navigation having come loose from the bottom of the window, which is exactly
 * what the first person to see it on a phone reported. A banner belongs against
 * an edge. Desks keep the bottom edge too, on the left, opposite the toasts
 * (where `--nav-bar-inset` is 0 and the offset collapses to plain padding).
 *
 * Everything portals into one host element rather than each banner reaching
 * for <body> on its own: two `fixed` banners pinned to the same edge sit on
 * top of each other. The host is a column, so a second prompt stacks under the
 * first. Portalling at all is required — a `fixed` child of an ancestor with a
 * transform or a filter anchors to that ancestor instead of the viewport, and
 * this app animates transforms all over the board.
 */

const HOST_ID = 'knowdown-prompt-stack'

/** The one fixed column every prompt renders into, created on first use. */
function promptHost(): HTMLElement {
  const existing = document.getElementById(HOST_ID)
  if (existing) return existing
  const host = document.createElement('div')
  host.id = HOST_ID
  // Above the header and the tab bar, below modals and below the toast rail
  // (z-[60]) — a prompt that has waited all session can yield to a message
  // about what just happened. `pointer-events-none` so the full-width column
  // doesn't swallow taps that miss a card; each card turns them back on.
  host.className = [
    'pointer-events-none fixed inset-x-0 bottom-[calc(var(--nav-bar-inset)+0.5rem)] z-50 flex flex-col items-center gap-2 px-4',
    // Desk: the bottom-left corner, clear of the bottom-right toast rail.
    'desk:inset-x-auto desk:bottom-0 desk:left-0 desk:items-start desk:p-4',
  ].join(' ')
  document.body.appendChild(host)
  return host
}

/**
 * A prompt card in the shared stack.
 *
 * `media` is the leading icon, `children` the copy, `actions` the buttons.
 * Below `sm` the actions drop to their own row: four things on one line
 * ("icon · sentence · button · dismiss") is what made this unreadable on a
 * phone, which is the only place an install prompt really matters.
 */
export function PromptBanner({
  media,
  children,
  actions,
  onDismiss,
  dismissLabel,
}: {
  media?: React.ReactNode
  children: React.ReactNode
  actions?: React.ReactNode
  onDismiss?: () => void
  dismissLabel?: string
}) {
  // The host is created in an effect so the portal target exists before React
  // reaches for it, rather than during the first render pass.
  const [host, setHost] = useState<HTMLElement | null>(null)
  useEffect(() => setHost(promptHost()), [])
  if (!host) return null

  return createPortal(
    <div className="plate pointer-events-auto flex w-full max-w-md flex-col gap-3 rounded-card p-3 shadow-elevated motion-safe:animate-slide-up sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {media}
        <div className="min-w-0 flex-1">{children}</div>
      </div>
      {(actions || onDismiss) && (
        <div className="flex shrink-0 items-center justify-end gap-2">
          {actions}
          {onDismiss && dismissLabel && (
            <button
              type="button"
              onClick={onDismiss}
              aria-label={dismissLabel}
              title={dismissLabel}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-btn text-ash transition-colors hover:bg-chalk/10 hover:text-chalk"
            >
              <X size={16} />
            </button>
          )}
        </div>
      )}
    </div>,
    host,
  )
}
