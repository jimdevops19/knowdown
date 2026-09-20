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
 * A tile's state is the *whole tile*, not a bar on the edge of it.
 *
 * This went through two versions before this one, and both of the earlier ones
 * were solving the same real problem from the wrong end. A tinted fill
 * (`bg-court/12`) has to stay faint to keep the option text legible, so under a
 * clock at arm's length "picked" and "not picked" were two shades of the same
 * dark rectangle. The fix at the time was a 4px bar of full-strength colour down
 * the left edge — which is legible, and is also precisely how a monitoring
 * dashboard marks the severity of a log row. It read as reporting, because that
 * is what the device is for.
 *
 * A game does the opposite: the colour *is* the object. Kahoot's answer grid is
 * four full-bleed coloured quadrants; Duolingo fills whole cards. Large
 * saturated areas are what the eye reads as play, and edge accents are what it
 * reads as status. So a picked tile is an orange tile, a right one is a mint
 * tile, a wrong one is a coral tile, and the legibility problem the tint had is
 * gone rather than worked around: at full strength the fill can carry dark ink,
 * which is both the highest-contrast pairing available and the rule every other
 * bright plate in this app already follows.
 *
 * What does *not* change is the reason the bar existed. The verdict is still
 * never carried by colour alone — the tick, the cross and the shake are all
 * still here, and they matter more now, not less, because a filled tile is a
 * bigger commitment to a hue.
 *
 * Each state also casts its own lip, so a tile is a pressable object like every
 * button, and the 4px of travel is the immediate confirmation that a tap landed
 * — which on a ten-second question is the difference between a player waiting
 * and a player tapping again.
 */
const STATE_CLASSES: Record<TileState, string> = {
  idle: 'pressable border-chalk/16 bg-raised text-chalk shadow-lip-plate hover:border-court hover:bg-panel',
  picked: 'border-transparent bg-court text-void shadow-lip-court',
  correct:
    'border-transparent bg-correct text-void shadow-lip-correct motion-safe:animate-verdict-correct',
  wrong: 'border-transparent bg-wrong text-void shadow-lip-wrong motion-safe:animate-verdict-wrong',
  dimmed: 'border-chalk/8 bg-panel/60 text-ash opacity-55',
}

/*
 * The option's letter. On a filled tile the key inverts to dark-on-dark-wash,
 * because the tile is now the bright surface and the badge has to sit *in* it
 * rather than glow on top of it.
 *
 * `idle` is the light key on a dark plate, and it is only used when a board
 * does not tell the tile which lane it is (see LANE_CLASSES).
 */
const LEAD_CLASSES: Record<TileState, string> = {
  idle: 'bg-chalk/12 text-chalk',
  picked: 'bg-void/20 text-void',
  correct: 'bg-void/20 text-void',
  wrong: 'bg-void/20 text-void',
  dimmed: 'bg-chalk/8 text-ash',
}

/*
 * The lanes: A is orange, B violet, C pink, D cyan.
 *
 * ── Why the key and not the whole tile ──────────────────────────────────────
 * Kahoot's answer grid is four full-bleed coloured quadrants, and that is the
 * obvious thing to copy here. It does not survive contact with this game: in
 * Knowdown a tile's *fill* is its state — orange means you picked it, mint that
 * you were right, coral that you were wrong — so painting the fill by position
 * would mean the same surface is saying two things at once, and a lime lane
 * sitting next to a mint verdict is the pair a player can least afford to
 * confuse under a ten-second clock.
 *
 * Kahoot can do it because Kahoot never has to show "picked, ruled on later":
 * it dims everything else the instant you tap. This board has to hold `picked`
 * on screen while the server rules.
 *
 * So the colour goes to the key instead — which is where the eye lands first on
 * a list of options anyway, and which the filled states already overwrite, so
 * nothing has to be given up. Four saturated chips on the grid, and the fill is
 * left to mean exactly one thing.
 *
 * Cycled by position rather than derived from the option, for the same reason
 * the rooms are (see RoomCircles): position is stable within a question, and a
 * question with five or eight options gets the same treatment as one with four
 * rather than running out of colours.
 *
 * Mint and coral are deliberately not in the set — they are the verdict, and a
 * lane that happened to be mint would be a tile wearing a right answer.
 */
const LANE_CLASSES = [
  'bg-court text-void',
  'bg-room-a text-void',
  'bg-room-b text-void',
  'bg-rival text-void',
] as const

export function AnswerTile({
  state = 'idle',
  disabled = false,
  onClick,
  children,
  /** A leading glyph or index — "A", "B", a number in an ordering list. */
  lead,
  /** Which lane this option is, zero-based, for the key's colour. Omitted by
   *  callers whose tiles are not a numbered set of choices. */
  lane,
  className = '',
}: {
  state?: TileState
  disabled?: boolean
  onClick?: () => void
  children: ReactNode
  lead?: ReactNode
  lane?: number
  className?: string
}) {
  // The lane colour is an `idle` decoration only: every other state paints the
  // whole tile, and a bright chip on a bright fill would be the one place in
  // the app where two saturated colours touch.
  const leadClass =
    state === 'idle' && lane !== undefined
      ? LANE_CLASSES[lane % LANE_CLASSES.length]
      : LEAD_CLASSES[state]
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={state === 'picked' || state === 'correct' || state === 'wrong'}
      className={`flex min-h-14 w-full items-center gap-3 rounded-tile border-2 px-4 py-3 text-left font-semibold disabled:pointer-events-none ${STATE_CLASSES[state]} ${className}`.trim()}
    >
      {lead !== undefined && (
        // The option's letter in widened display type — the lane number on a
        // start block. A generously rounded square rather than the hard 3px one
        // it was: at 28px that read as a cut corner from the broadcast scale,
        // and this is a chunky key on a chunky tile.
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] font-display text-sm font-bold [font-stretch:var(--display-wide)] ${leadClass}`}
        >
          {lead}
        </span>
      )}
      <span className="min-w-0 flex-1 break-words">{children}</span>
      {/* The second, non-colour channel on the verdict. `aria-hidden` because
          the state is already announced through `aria-pressed` plus the live
          region the board owns — two screen-reader announcements of the same
          fact is worse than one. */}
      {state === 'correct' && <Check size={22} strokeWidth={3} className="shrink-0" aria-hidden />}
      {state === 'wrong' && <X size={22} strokeWidth={3} className="shrink-0" aria-hidden />}
    </button>
  )
}
