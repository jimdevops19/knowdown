import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'
import { ToastContext, type Toast, type ToastApi, type ToastInput, type ToastLevel } from './toastContext'

/*
 * Transient feedback for something that finishes where the player isn't
 * looking: a rename that succeeded, a search that failed, a match that ended
 * while they were on another tab.
 *
 * The gap it fills is that a mutation rendering its result *in place* gives no
 * feedback at all once the thing it changed has left the screen. A toast
 * survives that, because it lives in a portal at the app root rather than
 * inside the component that fired the action.
 *
 * Deliberately *not* used for anything inside a live question. A card sliding
 * in over the board while somebody has six seconds to answer is worse than no
 * message at all — verdicts and opponent news are rendered by the board itself.
 */

const DEFAULT_DURATION = 5_000
/** Errors stay up longer: they usually need reading, not just noticing. */
const ERROR_DURATION = 10_000
/** Beyond this the oldest drops off, so a burst can't bury the page. */
const MAX_VISIBLE = 4

const STYLES: Record<ToastLevel, { icon: typeof Info; accent: string; ring: string }> = {
  info: { icon: Info, accent: 'text-volt', ring: 'border-volt/40' },
  success: { icon: CheckCircle2, accent: 'text-correct', ring: 'border-correct/40' },
  warning: { icon: AlertTriangle, accent: 'text-gold', ring: 'border-gold/40' },
  error: { icon: XCircle, accent: 'text-wrong', ring: 'border-wrong/40' },
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  // Timers live in a ref, not state: they are bookkeeping, and clearing one
  // must not schedule a render.
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  const dismiss = useCallback((id: string) => {
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
    setToasts((current) => current.filter((t) => t.id !== id))
  }, [])

  const show = useCallback(({ level, title, description, duration, id }: ToastInput) => {
    const toastId = id ?? `toast-${Math.random().toString(36).slice(2)}`
    const ms = duration ?? (level === 'error' ? ERROR_DURATION : DEFAULT_DURATION)
    const toast: Toast = { id: toastId, level, title, description, duration: ms }

    setToasts((current) => {
      const existing = current.findIndex((t) => t.id === toastId)
      const next =
        existing === -1 ? [...current, toast] : current.map((t) => (t.id === toastId ? toast : t))
      return next.slice(-MAX_VISIBLE)
    })

    // Re-showing an id restarts its clock, rather than leaving the old timer to
    // dismiss the replacement early.
    const previous = timers.current.get(toastId)
    if (previous) clearTimeout(previous)
    if (ms > 0) {
      timers.current.set(
        toastId,
        setTimeout(() => {
          timers.current.delete(toastId)
          setToasts((current) => current.filter((t) => t.id !== toastId))
        }, ms),
      )
    }
    return toastId
  }, [])

  // Sweep pending timers if the provider ever goes away mid-flight.
  useEffect(() => {
    const pending = timers.current
    return () => {
      pending.forEach(clearTimeout)
      pending.clear()
    }
  }, [])

  const api = useMemo<ToastApi>(
    () => ({
      show,
      dismiss,
      info: (title, options) => show({ level: 'info', title, ...options }),
      success: (title, options) => show({ level: 'success', title, ...options }),
      warning: (title, options) => show({ level: 'warning', title, ...options }),
      error: (title, options) => show({ level: 'error', title, ...options }),
    }),
    [show, dismiss],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  )
}

/*
 * The stack: bottom-right on a desktop, full-width along the bottom on a phone,
 * where a corner is a thumb's reach from nothing. Portalled to <body> because
 * any ancestor with `backdrop-filter` becomes the containing block for `fixed`
 * — and this app's every card has one.
 */
function ToastViewport({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: string) => void }) {
  if (toasts.length === 0) return null

  return createPortal(
    <div
      // `pointer-events-none` on the rail, restored per toast, so the empty
      // space beside one doesn't eat taps meant for the page.
      //
      // The bottom padding carries `--nav-bar-inset` (index.css) on top of the
      // usual 1rem: on phone chrome the foot of the viewport is the fixed nav
      // bar, and a toast at bottom-0 would land behind it.
      className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 pb-[calc(1rem+var(--nav-bar-inset))] sm:inset-x-auto sm:right-0 sm:items-end"
    >
      {toasts.map((toast) => (
        <ToastCard key={toast.id} toast={toast} onDismiss={() => onDismiss(toast.id)} />
      ))}
    </div>,
    document.body,
  )
}

function ToastCard({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const { icon: Icon, accent, ring } = STYLES[toast.level]

  return (
    <div
      role="status"
      aria-live={toast.level === 'error' ? 'assertive' : 'polite'}
      className={`glass pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-modal border ${ring} px-4 py-3 shadow-elevated motion-safe:animate-slide-up`}
    >
      <Icon size={18} className={`mt-0.5 shrink-0 ${accent}`} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-chalk">{toast.title}</p>
        {toast.description && <div className="mt-0.5 text-sm text-ash">{toast.description}</div>}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="-mr-1 -mt-1 shrink-0 rounded-btn p-1 text-ash transition-colors hover:bg-white/10 hover:text-chalk"
      >
        <X size={16} />
      </button>
    </div>
  )
}
