import { useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { GripVertical, RotateCcw } from 'lucide-react'
import type { OrderingQuestion } from '../../../lib/api/types'
import { Button } from '../../../components/Button'
import { type BoardProps } from './types'

/*
 * Put them in order: drag a card into a numbered slot.
 *
 * The board is two halves, and the split is the whole explanation of what this
 * question wants. Above: one **slot per position**, full width, drawn as an
 * answer tile with its fill taken away — a dashed outline the size and shape of
 * the thing that belongs in it. Below: the options as **small cards**, visibly
 * a different object from the slots, sitting loose in a pool. A blank that is
 * shaped like a filled answer and numbered 1..N is a question that cannot be
 * misread as "pick one".
 *
 * **Both gestures work, and tapping is the one that is fast.** The drag is what
 * makes the interaction legible — it is the gesture the layout suggests, and a
 * player who reaches for it must not find it dead. But a drag on a phone is a
 * press, a travel and a release, which is a long time out of a ten-second
 * clock, so a *tap* on a card drops it into the first free slot and a tap on a
 * filled slot sends the card back. The two share one code path: a pointer that
 * goes down and comes up without travelling more than a few pixels is a tap,
 * anything else is a drag. That threshold is also what keeps a scrolling thumb
 * from picking a card up by accident.
 *
 * The drag is pointer-events, not HTML5 drag-and-drop, and it has to be: the
 * `dragstart` API does not fire on touch at all, so the native version of this
 * board would be a desktop-only feature on a phone-first game. Dragging carries
 * a floating copy of the card under the finger and lights the slot it is over;
 * the card itself stays put until the drop, so a drag released over nothing
 * changes nothing.
 *
 * **Nothing here scrolls.** The pool is two cards to a row, wrapping onto as
 * many rows as it needs instead of running off the side — a horizontally scrolling strip of options
 * hides some of the answer behind a swipe, and on the one screen that is being
 * read against a clock, an option a player has to go looking for is an option
 * they do not consider. That is also why the cards are small and the copy is
 * expected to be short: every option and every slot has to be on a 390x844
 * screen at once, under the question. Each card is a fixed rectangle two lines
 * tall, so a name that wraps and a name that does not are the same object, and
 * the pool's height is set by how many options there are rather than by which
 * of them happened to be long.
 *
 * The options arrive shuffled, and here that is not cosmetic: the backend
 * stores these in their *correct* order, so an unshuffled payload would hand
 * over the answer while carefully omitting the field that states it.
 */
export function OrderingBoard({
  question,
  submission,
  verdict,
  locked,
  onAnswer,
}: BoardProps<OrderingQuestion>) {
  const total = question.options.length
  const [slots, setSlots] = useState<(number | null)[]>(() => Array<number | null>(total).fill(null))

  const committed = submission?.type === 'ordering' ? submission.option_ids : null
  const shown: (number | null)[] = committed ?? slots
  const complete = shown.every((optionId) => optionId !== null)
  // Frozen once the answer is on its way: the board stays as a record of what
  // was sent rather than an editor for something that can no longer change.
  const editable = !committed && !locked

  const pool = question.options.filter((option) => !shown.includes(option.id))
  const firstEmpty = shown.findIndex((optionId) => optionId === null)
  const optionsById = new Map(question.options.map((option) => [option.id, option]))

  // Live rects for the slots, so a drop can be resolved against where the
  // finger actually is. Read at drop time rather than kept in state: the row
  // heights change as cards leave the pool, and a cached rect would drop a card
  // into the slot that used to be there.
  const slotRefs = useRef<(HTMLElement | null)[]>([])
  const [drag, setDrag] = useState<Drag | null>(null)

  /** Move `optionId` into `to` (a slot index, or null for the pool), clearing
   *  wherever it was and bumping whatever it displaces back to the pool. */
  const move = (optionId: number, to: number | null) => {
    setSlots((current) => {
      const next = current.map((held) => (held === optionId ? null : held))
      if (to !== null) next[to] = optionId
      return next
    })
  }

  const slotIndexAt = (x: number, y: number) =>
    slotRefs.current.findIndex((element) => {
      if (!element) return false
      const rect = element.getBoundingClientRect()
      return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom
    })

  const startDrag = (event: ReactPointerEvent<HTMLElement>, optionId: number) => {
    if (!editable) return
    // Mouse: left button only. Touch and pen: every press.
    if (event.pointerType === 'mouse' && event.button !== 0) return
    // Optional: every browser that ships pointer events has this, jsdom does
    // not, and the board works without it — capture is what keeps the drag
    // alive when the finger leaves the card, not what starts it.
    event.currentTarget.setPointerCapture?.(event.pointerId)
    setDrag({
      optionId,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      x: event.clientX,
      y: event.clientY,
      moved: false,
      over: null,
    })
  }

  const moveDrag = (event: ReactPointerEvent<HTMLElement>) => {
    setDrag((current) => {
      if (!current || current.pointerId !== event.pointerId) return current
      const moved =
        current.moved ||
        Math.hypot(event.clientX - current.startX, event.clientY - current.startY) > DRAG_THRESHOLD
      const over = moved ? nullIfMissing(slotIndexAt(event.clientX, event.clientY)) : null
      return { ...current, x: event.clientX, y: event.clientY, moved, over }
    })
  }

  /** The one place a gesture becomes an edit. `tap` is what happens when the
   *  pointer never travelled — the quick path — and is also exactly what a
   *  keyboard `Enter` on the same control does, so the two never diverge. */
  const endDrag = (event: ReactPointerEvent<HTMLElement>, tap: () => void) => {
    setDrag((current) => {
      if (!current || current.pointerId !== event.pointerId) return null
      if (!current.moved) {
        tap()
      } else {
        const target = nullIfMissing(slotIndexAt(event.clientX, event.clientY))
        // Released over nothing: the card goes back to the pool if it was in a
        // slot, and stays put if it came from the pool. Either way the drop is
        // never silently "wherever it was last over".
        move(current.optionId, target)
      }
      return null
    })
  }

  const dragged = drag?.moved ? optionsById.get(drag.optionId) : undefined

  return (
    <div className="flex flex-col gap-3">
      {/* The answer being built. One row per position, always all of them: the
          shape of a finished answer is on screen before the first card lands. */}
      <ol className="flex flex-col gap-1.5">
        {shown.map((optionId, index) => {
          const option = optionId === null ? null : optionsById.get(optionId)
          const over = drag?.over === index
          return (
            <li
              key={index}
              ref={(element) => {
                slotRefs.current[index] = element
              }}
            >
              <button
                type="button"
                disabled={!option || !editable}
                onPointerDown={(event) => option && startDrag(event, option.id)}
                onPointerMove={moveDrag}
                onPointerUp={(event) => option && endDrag(event, () => move(option.id, null))}
                onPointerCancel={() => setDrag(null)}
                aria-label={
                  option
                    ? `Position ${index + 1}: ${option.text}. Activate to take it out`
                    : `Position ${index + 1}, empty`
                }
                className={`flex min-h-11 w-full touch-none select-none items-center gap-2.5 rounded-tile border px-3 py-2 text-left transition-colors disabled:pointer-events-none ${
                  option
                    ? SLOT_FILLED[verdict ?? 'picked']
                    : over
                      ? 'border-dashed border-volt bg-volt/10'
                      : editable && index === firstEmpty
                        ? 'border-dashed border-volt/55 bg-volt/5'
                        : 'border-dashed border-chalk/20 bg-panel/40'
                }`}
              >
                <span
                  className={`nums flex h-7 w-7 shrink-0 items-center justify-center rounded-[3px] font-display text-sm font-bold [font-stretch:var(--display-wide)] ${
                    option ? 'bg-chalk/10 text-ash' : 'bg-chalk/5 text-ash/70'
                  }`}
                >
                  {index + 1}
                </span>
                {option ? (
                  <span className="min-w-0 flex-1 break-words font-medium text-chalk">
                    {option.text}
                  </span>
                ) : (
                  <span className="min-w-0 flex-1 text-sm text-ash/70">
                    {index === firstEmpty ? 'Drop or tap a card here' : `${ordinal(index + 1)}`}
                  </span>
                )}
                {option && editable && (
                  <GripVertical size={16} className="shrink-0 text-ash/60" aria-hidden />
                )}
              </button>
            </li>
          )
        })}
      </ol>

      {/* The pool: two to a row, every card the same rectangle. See the note
          at the top of the file — it wraps downward and never scrolls. */}
      {pool.length > 0 && (
        <div className="grid grid-cols-2 gap-2" aria-label="Options left to place">
          {pool.map((option) => (
            <button
              key={option.id}
              type="button"
              disabled={!editable}
              onPointerDown={(event) => startDrag(event, option.id)}
              onPointerMove={moveDrag}
              onPointerUp={(event) =>
                endDrag(event, () => firstEmpty !== -1 && move(option.id, firstEmpty))
              }
              onPointerCancel={() => setDrag(null)}
              aria-label={
                firstEmpty === -1
                  ? option.text
                  : `${option.text}. Activate to put it in position ${firstEmpty + 1}`
              }
              className={`flex min-h-[3.25rem] touch-none select-none items-center justify-center rounded-[6px] border border-chalk/15 border-l-2 border-l-court bg-raised px-2.5 py-2 text-center text-sm font-medium leading-snug text-chalk transition-transform disabled:pointer-events-none disabled:opacity-55 ${
                drag?.optionId === option.id && drag.moved
                  ? 'opacity-35'
                  : 'hover:border-l-volt active:scale-[0.97]'
              }`}
            >
              {/* Two lines' worth of box whether or not the text needs two:
                  the cards are one object repeated, and a row of rectangles at
                  two different heights reads as a mistake rather than as a
                  longer label. `text-balance` splits "Golden State Warriors"
                  into two even lines instead of one full line and one orphan. */}
              <span className="text-balance break-words">{option.text}</span>
            </button>
          ))}
        </div>
      )}

      {!committed && (
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="lg"
            disabled={locked || pool.length === total}
            onClick={() => setSlots(Array<number | null>(total).fill(null))}
            aria-label="Take every card back"
          >
            <RotateCcw size={18} aria-hidden />
          </Button>
          <Button
            variant="accent"
            size="lg"
            className="flex-1"
            // A partial sequence is refused here rather than sent: the server
            // scores the whole arrangement, so half an order is not a partly
            // right answer, it is a malformed one. The label names the slot
            // still open — an instruction, where "2 of 4 placed" is a status.
            disabled={locked || !complete}
            onClick={() => onAnswer({ type: 'ordering', option_ids: shown as number[] })}
          >
            {complete ? 'Lock in this order' : `Fill the ${ordinal(firstEmpty + 1)} slot`}
          </Button>
        </div>
      )}

      {/* The card under the finger. Fixed and `pointer-events-none` so it never
          becomes its own drop target, and rendered only once the pointer has
          travelled — a tap must not flash a floating card. */}
      {dragged && drag && (
        <div
          className="pointer-events-none fixed z-50 flex min-h-[3.25rem] w-[45vw] max-w-[13rem] -translate-x-1/2 -translate-y-1/2 items-center justify-center text-balance rounded-[6px] border border-volt bg-raised px-2.5 py-2 text-center text-sm font-medium leading-snug text-chalk shadow-edge-volt"
          style={{ left: drag.x, top: drag.y }}
          aria-hidden
        >
          {dragged.text}
        </div>
      )}
    </div>
  )
}

/** A pointer that is holding a card. `moved` is what separates a drag from a
 *  tap, and `over` is the slot the drop would land in right now. */
interface Drag {
  optionId: number
  pointerId: number
  startX: number
  startY: number
  x: number
  y: number
  moved: boolean
  over: number | null
}

/** Far enough that the finger meant it, short enough that a drag feels picked
 *  up rather than dragged into life. */
const DRAG_THRESHOLD = 6

/** A filled slot wears the same left-edge bar as an answer tile, and the same
 *  verdict colours — this is the control the server's ruling lands on. */
const SLOT_FILLED: Record<'picked' | 'correct' | 'wrong', string> = {
  picked: 'border-chalk/8 border-l-4 border-l-court bg-court/12',
  correct: 'border-chalk/8 border-l-4 border-l-correct bg-correct/12',
  wrong: 'border-chalk/8 border-l-4 border-l-wrong bg-wrong/10',
}

/** `findIndex` says "nowhere" with -1; the rest of this file says it with
 *  null, because -1 is a valid array index away from being a silent bug. */
const nullIfMissing = (index: number) => (index === -1 ? null : index)

/** 1 → "1st". Options top out at eight (`OPTION_LETTERS`), so the teens the
 *  general rule exists for cannot occur — but it costs nothing to be right. */
function ordinal(n: number) {
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? 'th' : (['th', 'st', 'nd', 'rd'][n % 10] ?? 'th')
  return `${n}${suffix}`
}
