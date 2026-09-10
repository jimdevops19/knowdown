import type { ReactNode } from 'react'

/*
 * A labelled form field: the label above the control, and the error under it.
 *
 * The error is rendered by the field rather than by each form, so a server
 * refusal reaches the right place by naming the field — see `fieldErrors()` in
 * lib/api/errors, which flattens the backend's `details` map. `role="alert"`
 * so a screen reader announces the refusal rather than leaving it to be found.
 */
export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: ReactNode
  error?: string
  children: ReactNode
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-ash">{label}</span>
      {children}
      {error ? (
        <span role="alert" className="text-sm text-wrong">
          {error}
        </span>
      ) : (
        hint && <span className="text-xs text-ash/70">{hint}</span>
      )}
    </label>
  )
}
