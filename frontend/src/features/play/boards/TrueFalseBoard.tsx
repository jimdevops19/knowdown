import { Check, X } from 'lucide-react'
import type { TrueFalseQuestion } from '../../../lib/api/types'
import { type BoardProps } from './types'

/*
 * True or false — the fastest question in the catalog, and the board is shaped
 * to let it be.
 *
 * The two buttons are the client's: the payload carries no options at all,
 * because the only thing a true/false question has to hide is one boolean
 * column called `answer`, and the play-time serializer makes that column
 * undeclarable rather than merely omitted.
 *
 * Two big targets side by side, always — not stacked on a phone like the other
 * boards. With only two choices there is no list to read down, so the win is in
 * putting both under a thumb at once; the answer is a reflex, and the layout
 * should not make it a scroll.
 */
export function TrueFalseBoard({
  submission,
  verdict,
  locked,
  onAnswer,
}: BoardProps<TrueFalseQuestion>) {
  const picked = submission?.type === 'true-false' ? submission.answer : null

  return (
    <div className="grid grid-cols-2 gap-3">
      <Choice
        value
        picked={picked}
        verdict={verdict}
        locked={locked}
        onPick={() => onAnswer({ type: 'true-false', answer: true })}
      />
      <Choice
        value={false}
        picked={picked}
        verdict={verdict}
        locked={locked}
        onPick={() => onAnswer({ type: 'true-false', answer: false })}
      />
    </div>
  )
}

function Choice({
  value,
  picked,
  verdict,
  locked,
  onPick,
}: {
  value: boolean
  picked: boolean | null
  verdict: 'correct' | 'wrong' | null
  locked: boolean
  onPick: () => void
}) {
  const isPicked = picked === value

  /*
   * The same grammar as <AnswerTile>: the state is the whole button, it casts
   * its own lip, and it travels through that lip when pressed.
   *
   * ── Why the two choices are not mint and coral ──────────────────────────────
   * They were: True hovered green, False hovered red, and the tick and cross
   * were painted in the verdict colours. It reads well right up until somebody
   * answers False and is right — at which point they are looking at a mint
   * panel with a red cross on it, and the two halves of the screen are making
   * opposite claims. In this app mint and coral mean *the server ruled*, and
   * nothing a player can choose before that is allowed to borrow them.
   *
   * So both choices are the same neutral plate, the word carries the meaning in
   * display caps, and the tick and cross stay as shape alone — which is the job
   * they were actually doing.
   */
  const tone = isPicked
    ? verdict === 'correct'
      ? 'border-transparent bg-correct text-void shadow-lip-correct motion-safe:animate-verdict-correct'
      : verdict === 'wrong'
        ? 'border-transparent bg-wrong text-void shadow-lip-wrong motion-safe:animate-verdict-wrong'
        : 'border-transparent bg-court text-void shadow-lip-court'
    : locked
      ? 'border-chalk/8 bg-panel/60 text-ash opacity-55'
      : 'pressable border-chalk/16 bg-raised text-chalk shadow-lip-plate hover:border-court hover:bg-panel'

  const Icon = value ? Check : X

  return (
    <button
      type="button"
      disabled={locked}
      aria-pressed={isPicked}
      onClick={onPick}
      className={`flex min-h-28 flex-col items-center justify-center gap-2 rounded-tile border-2 disabled:pointer-events-none ${tone}`}
    >
      {/* Both glyphs inherit the button's ink, so they invert onto the dark ink
          of a filled state along with the label rather than staying bright. */}
      <Icon size={30} strokeWidth={3} aria-hidden />
      <span className="font-display text-lg font-bold uppercase tracking-wide">
        {value ? 'True' : 'False'}
      </span>
    </button>
  )
}
