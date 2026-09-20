import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

/*
 * The app's one way to interrupt the page.
 *
 * `ConfirmDialog` used to carry this plumbing itself, and its docstring said
 * why: there was exactly one thing in the app that needed to interrupt a player
 * rather than render in place, and a layer with one caller is a layer that has
 * not earned its name. There are two now — the box score reveals a long answer
 * behind a button — so the plumbing moves here and `ConfirmDialog` becomes what
 * it always described itself as: a *yes/no gate*, which is a modal plus a
 * decision, not a different kind of window.
 *
 * What lives here is the part both need and neither should re-derive:
 *
 *  · **Portalled to `document.body`.** Any ancestor with `backdrop-filter`
 *    becomes the containing block for `fixed`, and this app's every card has
 *    one — a modal rendered in place would be clipped inside whichever card
 *    opened it. `Toast.tsx` is portalled for the same reason.
 *  · **Escape and the scrim both close it.** A window the page put in your way
 *    should be at least as easy to leave as it was to enter.
 *  · **The body does not scroll behind it.** On a phone, a modal over a
 *    scrollable page means a flick at the list scrolls the page instead, and
 *    the content the modal exists to show slides out from under it.
 *
 * What does *not* live here is anything about what a modal is for. No icon, no
 * tone, no buttons: `ConfirmDialog` supplies its own alarm colouring and its
 * own pair of verbs, and a reveal supplies a list. A prop for each would make
 * this the union of its callers rather than the thing they have in common.
 */
export interface ModalProps {
  open: boolean
  title: string
  /** Sits under the title, for the sentence that frames what is below it. */
  description?: string
  onClose: () => void
  children: ReactNode
  /** `alertdialog` for a modal gating a decision, which is what tells a screen
   *  reader to announce it rather than wait to be asked. Plain `dialog`
   *  otherwise — a list of answers is information, not an alarm. */
  role?: 'dialog' | 'alertdialog'
  /** Border colour, for a caller that means to look like a warning. */
  className?: string
  /** The row of actions along the bottom, if the caller has any. */
  footer?: ReactNode
  /** How wide the window may get. The default suits a sentence and a pair of
   *  buttons, which is what every modal in this app was until the question
   *  editor — a form with option rows in it needs the room, and cramming one
   *  into a reading-width column makes every row wrap. */
  widthClass?: string
}

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  role = 'dialog',
  className = 'border-chalk/12',
  footer,
  widthClass = 'max-w-md',
}: ModalProps) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  // Restores whatever the page had rather than hard-setting `visible` on the
  // way out: two modals open at once (a confirm raised from inside a reveal)
  // would otherwise have the first to close unlock the page under the second.
  useEffect(() => {
    if (!open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [open])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-void/70 p-4 motion-safe:animate-fade-in"
      onClick={onClose}
    >
      <div
        role={role}
        aria-modal="true"
        aria-labelledby="modal-title"
        aria-describedby={description ? 'modal-description' : undefined}
        // `max-h` + the scrolling body below are what keep a forty-cell grid
        // from running off the bottom of a phone with no way back to the close
        // button.
        className={`plate flex max-h-[85vh] w-full ${widthClass} flex-col rounded-modal border p-5 shadow-elevated motion-safe:animate-slide-up ${className}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h2 id="modal-title" className="text-base font-semibold text-chalk">
              {title}
            </h2>
            {description && (
              <p id="modal-description" className="mt-1 text-sm text-ash">
                {description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-mr-1 -mt-1 shrink-0 rounded-tile p-1 text-ash hover:bg-raised hover:text-chalk"
          >
            <X size={18} aria-hidden />
          </button>
        </div>

        <div className="-mx-1 mt-4 min-h-0 flex-1 overflow-y-auto px-1">{children}</div>

        {footer && <div className="mt-5 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}
