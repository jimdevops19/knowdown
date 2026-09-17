import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle } from 'lucide-react'
import { Button } from './Button'

/*
 * A blocking yes/no gate for an action that cannot be undone — the app's
 * first modal, built for forfeiting a live match. There is deliberately no
 * generic "Modal" underneath it: this app has exactly one thing so far that
 * needs to interrupt the player rather than render in place (see `Toast.tsx`'s
 * own docstring on why toasts refuse that job), so the portal-to-`document
 * .body` plumbing lives here instead of behind a layer with only one caller.
 *
 * Portalled for the same reason `Toast.tsx` is: any ancestor with
 * `backdrop-filter` becomes the containing block for `fixed`, and this app's
 * every card has one.
 */
export interface ConfirmDialogProps {
  open: boolean
  title: string
  description?: string
  confirmLabel: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  // Escape backs out the same way tapping the scrim does — a modal gating a
  // one-way door should be at least as easy to leave as it is to enter.
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onCancel])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-void/70 p-4 motion-safe:animate-fade-in"
      onClick={onCancel}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby={description ? 'confirm-dialog-description' : undefined}
        className="plate w-full max-w-sm rounded-modal border border-wrong/40 p-5 shadow-elevated motion-safe:animate-slide-up"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <AlertTriangle size={20} className="mt-0.5 shrink-0 text-wrong" aria-hidden />
          <div className="min-w-0 flex-1">
            <h2 id="confirm-dialog-title" className="text-base font-semibold text-chalk">
              {title}
            </h2>
            {description && (
              <p id="confirm-dialog-description" className="mt-1 text-sm text-ash">
                {description}
              </p>
            )}
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
