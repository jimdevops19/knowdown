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

/*
 * A tile carries its state on its *left edge* as a 4px bar, not as a wash of
 * tint across the whole surface.
 *
 * This is the one place the layout changed rather than just the colours. A
 * tinted fill has to stay faint to keep the option text legible, so at a metre
 * away under a clock, "picked" and "not picked" were two shades of the same
 * dark rectangle. A solid bar of full-strength colour down one edge reads as a
 * marked tile from across the room, costs the text nothing, and is exactly how
 * a broadcast scoreboard marks a row. The fill stays as a whisper behind it.
 */
const STATE_CLASSES: Record<TileState, string> = {
  idle: 'border-l-chalk/15 bg-panel text-chalk hover:border-l-court hover:bg-raised active:scale-[0.985]',
  picked: 'border-l-court bg-court/12 text-chalk',
  correct: 'border-l-correct bg-correct/12 text-chalk motion-safe:animate-verdict-correct',
  wrong: 'border-l-wrong bg-wrong/10 text-chalk motion-safe:animate-verdict-wrong',
  dimmed: 'border-l-chalk/8 bg-panel/60 text-ash opacity-55',
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
      className={`flex min-h-14 w-full items-center gap-3 rounded-tile border border-chalk/8 border-l-4 px-4 py-3 text-left font-medium transition-all duration-150 disabled:pointer-events-none ${STATE_CLASSES[state]} ${className}`.trim()}
    >
      {lead !== undefined && (
        // The option's letter, set as a hard square in widened display type —
        // the lane number on a start block. Square rather than rounded because
        // it is the smallest element on the board, and at 28px a rounded
        // rectangle is indistinguishable from a circle.
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[3px] bg-chalk/10 font-display text-sm font-bold [font-stretch:var(--display-wide)] text-ash">
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
