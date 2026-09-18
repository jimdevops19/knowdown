import { AlertTriangle } from 'lucide-react'
import { Button } from './Button'
import { Modal } from './Modal'

/*
 * A blocking yes/no gate for an action that cannot be undone — built for
 * forfeiting a live match, and still the only caller.
 *
 * It used to own the portal, the Escape handler and the scrim itself, because
 * it was the app's only modal and a generic layer with one caller is a layer
 * that has not earned its name. `Modal` exists now (the box score reveals long
 * answers behind a button), so what is left here is the part that was never
 * generic: an alarm colour, a warning icon, and a pair of verbs one of which is
 * destructive.
 *
 * `alertdialog` rather than `dialog` is the one accessibility difference and it
 * is deliberate — it tells a screen reader to interrupt, which is right for a
 * one-way door and wrong for a list of answers.
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
  return (
    <Modal
      open={open}
      title={title}
      onClose={onCancel}
      role="alertdialog"
      className="max-w-sm border-wrong/40"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {/* The icon sits beside the caller's own description rather than being a
          prop on `Modal`: it is this dialog's alarm, and a `Modal` that took an
          icon would be growing a field for one caller's tone. A confirm with no
          description is legal — the title is sometimes the whole question — and
          then this renders as the icon alone, which is what it did before. */}
      <div className="flex items-start gap-3">
        <AlertTriangle size={20} className="mt-0.5 shrink-0 text-wrong" aria-hidden />
        {description && <p className="text-sm text-ash">{description}</p>}
      </div>
    </Modal>
  )
}
