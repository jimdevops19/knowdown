import type { ReactNode } from 'react'
import { Check, X } from 'lucide-react'

/*
 * The app's signature control: one option, as a big tappable tile.
 *
 * Everything about it is decided by the ten-second clock it lives under.
 *
 *  - **It is at least 56px tall and full-width in its column.** A player is
 *    reading, deciding and tapping in under ten seconds, one-handed; a mis-tap
 *    is not a nuisance here, it is a lost question and rating with it.
 *  - **The verdict is never colour alone.** A correct tile gets a tick and a
 *    green ring; a wrong one gets a cross, a red ring *and* a shake. Roughly 1
 *    in 12 men cannot separate this green from this red, and "did I get it
 *    right" is not something to leave to a hue.
 *  - **`picked` and `correct` are different states.** The board shows what this
 *    player chose the moment they choose it — before the server has said
 *    anything — because a tile that stays inert while a round trip happens
 *    reads as a tap that didn't register, and the player taps again.
 *
 * The verdict props deliberately do not include "which option was the right
 * one": the server does not publish the answer key, only whether *you* were
 * right (see `lib/realtime/messages.ts`). So a wrong tile shows that it was
 * wrong, and the correct option is not revealed — the question can come up
 * again in a later match.
 */
export type TileState =
  /** Open, untouched. */
  | 'idle'
  /** This player picked it; the server hasn't ruled yet. */
  | 'picked'
  /** Picked, and the server said it was right. */
  | 'correct'
  /** Picked, and the server said it was wrong. */
  | 'wrong'
  /** The question is closed (or the clock ran out) and this wasn't picked. */
  | 'dimmed'

const STATE_CLASSES: Record<TileState, string> = {
  idle: 'border-white/10 bg-panel/80 text-chalk hover:border-court/60 hover:bg-court/10 active:scale-[0.985]',
  picked: 'border-court bg-court/25 text-chalk shadow-glow-violet',
  correct: 'border-correct bg-correct/20 text-chalk shadow-glow-correct motion-safe:animate-verdict-correct',
  wrong: 'border-wrong bg-wrong/15 text-chalk shadow-glow-wrong motion-safe:animate-verdict-wrong',
  dimmed: 'border-white/8 bg-panel/50 text-ash opacity-60',
}

export function AnswerTile({
  state = 'idle',
  disabled = false,
  onClick,
  children,
  /** A leading glyph or index — "A", "B", a number in an ordering list. */
  lead,
  className = '',
}: {
  state?: TileState
  disabled?: boolean
  onClick?: () => void
  children: ReactNode
  lead?: ReactNode
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={state === 'picked' || state === 'correct' || state === 'wrong'}
      className={`flex min-h-14 w-full items-center gap-3 rounded-tile border-2 px-4 py-3 text-left font-medium transition-all duration-150 disabled:pointer-events-none ${STATE_CLASSES[state]} ${className}`.trim()}
    >
      {lead !== undefined && (
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/8 font-display text-sm font-bold text-ash">
          {lead}
        </span>
      )}
      <span className="min-w-0 flex-1 break-words">{children}</span>
      {/* The second, non-colour channel on the verdict. `aria-hidden` because
          the state is already announced through `aria-pressed` plus the live
          region the board owns — two screen-reader announcements of the same
          fact is worse than one. */}
      {state === 'correct' && <Check size={20} className="shrink-0 text-correct" aria-hidden />}
      {state === 'wrong' && <X size={20} className="shrink-0 text-wrong" aria-hidden />}
    </button>
  )
}
