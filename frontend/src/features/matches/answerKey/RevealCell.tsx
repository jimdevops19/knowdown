import { useState, type ReactNode } from 'react'
import { Modal } from '../../../components/Modal'
import type { Reveal } from './reveals'

/*
 * One answer, in a table cell — inline if it fits, behind a button if it does
 * not.
 *
 * Shared by the two things a box score row can be showing: what a player said
 * (`describeSubmission`) and what was actually right (`describeAnswerKey`).
 * They differ in what they mean and not at all in how they have to be laid out,
 * which is why the layout is here and the meaning is in the builders — a set of
 * six picks is six chips whether it was the key or somebody's guess, and having
 * written that twice would guarantee the two drifting.
 *
 * `tone` is the caller's, since it is the part that *is* about meaning: a
 * verdict colour for a player's row, the neutral gold for the key.
 */
export function RevealCell({
  reveal,
  tone,
  icon,
}: {
  reveal: Reveal
  /** Text colour classes — the caller owns this; see above. */
  tone: string
  /** Sits before the label. A tick, a cross, a key. */
  icon?: ReactNode
}) {
  const [open, setOpen] = useState(false)

  if (reveal.kind === 'inline') {
    return (
      <span className={`flex items-center gap-1.5 ${tone}`}>
        {icon}
        {reveal.content}
      </span>
    )
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`flex items-center gap-1.5 rounded-tile underline decoration-current/40 underline-offset-4 hover:decoration-current ${tone}`}
      >
        {icon}
        {reveal.label}
      </button>
      <Modal
        open={open}
        title={reveal.title}
        description={reveal.description}
        onClose={() => setOpen(false)}
      >
        {reveal.body}
      </Modal>
    </>
  )
}
