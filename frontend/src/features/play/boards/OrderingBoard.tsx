import { useState } from 'react'
import { RotateCcw } from 'lucide-react'
import type { OrderingQuestion } from '../../../lib/api/types'
import { AnswerTile, type TileState } from '../AnswerTile'
import { Button } from '../../../components/Button'
import { type BoardProps } from './types'

/*
 * Put them in order.
 *
 * **Tap-to-place, not drag-and-drop.** Dragging is the obvious interaction and
 * the wrong one here: a drag on a phone is a long press, a move and a release —
 * three seconds of a ten-second clock for one item — and it fights the page's
 * own scroll on exactly the screen that must not scroll. Tapping each item in
 * the order you want them is one gesture per item, works one-handed, and cannot
 * be lost to a mis-grab.
 *
 * The chosen positions are numbered as they are picked, so the arrangement is
 * always readable off the board without a second list beside it. `Reset` exists
 * because a mis-tap here is not one wrong answer but a wrong *sequence*, and
 * re-tapping to undo would be ambiguous.
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
  const [order, setOrder] = useState<number[]>([])

  const committed = submission?.type === 'ordering' ? submission.option_ids : null
  const shown = committed ?? order
  const complete = shown.length === question.options.length

  const place = (optionId: number) => {
    if (shown.includes(optionId)) return
    setOrder((current) => [...current, optionId])
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ash">{question.instruction}</p>

      <div className="grid gap-2">
        {question.options.map((option) => {
          const position = shown.indexOf(option.id)
          const placed = position !== -1
          const state: TileState = placed
            ? (verdict ?? 'picked')
            : locked
              ? 'dimmed'
              : 'idle'
          return (
            <AnswerTile
              key={option.id}
              state={state}
              // The position, once it has one — the whole point of the board.
              // A dot rather than a blank for the unplaced ones, so the row of
              // leads reads as a column of slots waiting to be filled.
              lead={placed ? position + 1 : '·'}
              disabled={locked || placed}
              onClick={() => place(option.id)}
            >
              {option.text}
            </AnswerTile>
          )
        })}
      </div>

      {!committed && (
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="lg"
            disabled={locked || shown.length === 0}
            onClick={() => setOrder([])}
            aria-label="Start the order again"
          >
            <RotateCcw size={18} aria-hidden />
          </Button>
          <Button
            variant="accent"
            size="lg"
            className="flex-1"
            // A partial sequence is refused here rather than sent: the server
            // scores the whole arrangement, so half an order is not a partly
            // right answer, it is a malformed one.
            disabled={locked || !complete}
            onClick={() => onAnswer({ type: 'ordering', option_ids: order })}
          >
            {complete
              ? 'Lock in this order'
              : `${shown.length} of ${question.options.length} placed`}
          </Button>
        </div>
      )}
    </div>
  )
}
