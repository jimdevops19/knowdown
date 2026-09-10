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
  const tone = isPicked
    ? verdict === 'correct'
      ? 'border-correct bg-correct/20 shadow-glow-correct motion-safe:animate-verdict-correct'
      : verdict === 'wrong'
        ? 'border-wrong bg-wrong/15 shadow-glow-wrong motion-safe:animate-verdict-wrong'
        : 'border-court bg-court/25 shadow-glow-violet'
    : locked
      ? 'border-white/8 bg-panel/50 opacity-55'
      : value
        ? 'border-white/10 bg-panel/80 hover:border-correct/50 hover:bg-correct/10 active:scale-[0.985]'
        : 'border-white/10 bg-panel/80 hover:border-wrong/50 hover:bg-wrong/10 active:scale-[0.985]'

  const Icon = value ? Check : X

  return (
    <button
      type="button"
      disabled={locked}
      aria-pressed={isPicked}
      onClick={onPick}
      className={`flex min-h-28 flex-col items-center justify-center gap-2 rounded-tile border-2 transition-all duration-150 disabled:pointer-events-none ${tone}`}
    >
      <Icon size={30} className={value ? 'text-correct' : 'text-wrong'} aria-hidden />
      <span className="font-display text-lg font-bold uppercase tracking-wide text-chalk">
        {value ? 'True' : 'False'}
      </span>
    </button>
  )
}
