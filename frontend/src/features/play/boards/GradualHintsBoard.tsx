import { useState } from 'react'
import { Lock } from 'lucide-react'
import type { AnswerFieldSubmission, GradualHintsQuestion } from '../../../lib/api/types'
import { Input } from '../../../components/Input'
import { Button } from '../../../components/Button'
import { type BoardProps } from './types'
import { useAutoSubmitAtDeadline } from './useAutoSubmitAtDeadline'

/*
 * "Guess the game" — a question that is still being asked while you answer it.
 *
 * The clues arrive one at a time, hardest first, on the server's clock; this
 * board draws however many have landed and a placeholder for each one still
 * coming. Four decisions are worth stating, because each is the opposite of
 * what the obvious implementation does.
 *
 * **The empty slots are drawn, not hidden.** A board that grew a line every few
 * seconds would shift the inputs down the screen under the player's thumb,
 * which on a phone means a mistap at the worst possible moment. Reserving the
 * space up front also *is* the question: five slots says "there are four more
 * clues coming, and answering now is worth more than waiting for them" without
 * a word of instruction.
 *
 * **Nothing counts down to the next clue.** The player already has one clock to
 * watch and it is the one that matters; a second timer beside it would compete
 * for the same glance and suggest that waiting is the plan. The new clue
 * announces itself by appearing.
 *
 * **The boxes are a grid, not a row that wraps.** Every field takes the same
 * column — two across on a phone, three from `sm` up — so however many boxes a
 * question asks for, they line up on both edges. Sizing each box to its own
 * `field.kind` instead (a short one for a number, whatever was left of the row
 * for text) is what this used to do, and on a 390px phone it laid "Year /
 * Round / Game number" out as a thumbnail box, a box running to the right
 * edge, and a third stranded full-width on a line of its own: three widths,
 * none of them agreeing, for three boxes of equal importance. The kind still
 * decides the *keyboard* and the length cap, which is the part of it a player
 * can feel; it no longer decides the width. A lone box takes the full row —
 * half a row with nothing beside it is just a gap.
 *
 * Bottoms align (`items-end`), not tops: a label that wraps to two lines
 * ("Season ending year" beside "Wins") would otherwise push its own box a line
 * lower than its neighbour's, and a row of boxes at two different heights
 * reads as a mistake rather than as a longer label.
 *
 * **A partial answer is a real answer**, exactly as on the matrix board: the
 * server credits this question per field, so filling in the two boxes you know
 * and sending is the correct play rather than a concession. Hence the submit
 * button goes live on the first filled box instead of waiting for a complete
 * set — and says how many of how many are going, so nobody sends two of three
 * believing they sent everything. The boxes are also sent **at the wire** if the
 * button never gets pressed: two fields right and never submitted is worth
 * nothing, and on the one board where waiting for another clue is a real
 * strategy, the clock catching somebody mid-thought must not cost them
 * everything they had (`useAutoSubmitAtDeadline`).
 */
export function GradualHintsBoard({
  question,
  hints,
  submission,
  verdict,
  deadlineAt,
  locked,
  onAnswer,
}: BoardProps<GradualHintsQuestion>) {
  const [values, setValues] = useState<Record<number, string>>({})

  const committed =
    submission?.type === 'gradual-hints'
      ? Object.fromEntries(
          submission.answer_fields.map((field) => [field.field_id, field.text]),
        )
      : null
  const shown = committed ?? values

  const filled = question.answer_fields.filter(
    (field) => (shown[field.id] ?? '').trim().length > 0,
  )

  const build = () => {
    const answer_fields: AnswerFieldSubmission[] = filled.map((field) => ({
      field_id: field.id,
      // Verbatim, like every typed answer in this app: folding and trimming are
      // the evaluator's business, and what gets recorded should be the thing
      // the player can be shown afterwards.
      text: shown[field.id],
    }))
    return answer_fields.length === 0 ? null : { type: 'gradual-hints' as const, answer_fields }
  }

  const submit = () => {
    const submission = build()
    if (submission !== null) onAnswer(submission)
  }

  useAutoSubmitAtDeadline({
    deadlineAt,
    committed: committed !== null,
    locked,
    build,
    onAnswer,
  })

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      {/* `aria-live="polite"`: a clue appearing is new information the sighted
          player gets for free, and a screen reader user would otherwise never
          learn it arrived. Polite rather than assertive — it must not interrupt
          somebody mid-way through hearing the field they are typing into. */}
      <ol className="flex flex-col gap-2" aria-live="polite" aria-label="Clues">
        {Array.from({ length: question.hint_count }, (_, index) => {
          const text = hints[index]
          return (
            <li
              key={index}
              // `min-h` matching one filled line, and the placeholder centred
              // in it rather than sized by its own bar: an empty slot and a
              // one-line clue are then exactly the same height, so a clue
              // arriving repaints in place instead of nudging every box below
              // it down by the few pixels a 16px bar differs from a 20px line
              // of text. Small, and it lands while somebody is typing.
              // (The reveal animation is a `transform`, which moves no layout.)
              className={`flex min-h-[2.375rem] items-center rounded-tile border px-3 py-2 text-sm ${
                text
                  ? 'border-chalk/8 bg-panel/60 text-chalk motion-safe:animate-slide-up'
                  : 'border-dashed border-chalk/10 bg-transparent'
              }`}
            >
              {text ? (
                <span>
                  <span className="mr-2 font-display text-xs font-semibold text-ash">
                    {index + 1}
                  </span>
                  {text}
                </span>
              ) : (
                // The slot a clue has not filled yet. Hidden from screen
                // readers: "blank, blank, blank" is noise, and the count is
                // already announced by the list's own label.
                <span aria-hidden className="block h-4 w-2/3 rounded bg-chalk/5" />
              )}
            </li>
          )
        })}
      </ol>

      <div className="grid grid-cols-2 items-end gap-x-3 gap-y-3 sm:grid-cols-3">
        {question.answer_fields.map((field, index) => {
          const numeric = field.kind === 'number'
          return (
            <label
              key={field.id}
              // One column each, and the whole row when there is only one box
              // to put in it. `min-w-0` because a grid track's default minimum
              // is its content: without it a long label would push its own
              // column wider than the share it was given and take the grid off
              // the side of the screen.
              className="flex min-w-0 flex-col gap-1 [&:only-child]:col-span-full"
            >
              <span className="font-display text-xs font-semibold uppercase tracking-wide text-ash">
                {field.label}
              </span>
              <Input
                // Only the first box takes focus, and only on mount — the board
                // is remounted per question (see QuestionBoard's `key`), so it
                // never steals the caret from somebody already typing in the
                // third box when a clue lands.
                autoFocus={index === 0}
                value={shown[field.id] ?? ''}
                onChange={(event) =>
                  setValues((current) => ({
                    ...current,
                    [field.id]: event.target.value,
                  }))
                }
                disabled={locked}
                // Never `type="number"`: it brings spinner arrows that a mistap
                // increments, a scroll wheel that changes a value the player is
                // looking at, and a browser that silently drops what it cannot
                // parse. `inputMode` gets the phone keypad, which is the only
                // part of it worth having.
                inputMode={numeric ? 'numeric' : undefined}
                maxLength={numeric ? 8 : 255}
                // Off for the reason the free-text board turns them off: a phone
                // keyboard correcting a name, or offering this player's own
                // previous answers, is a cheat sheet built out of their history.
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="off"
                spellCheck={false}
                className={
                  verdict === 'correct'
                    ? 'border-correct focus:border-correct focus:ring-correct/25'
                    : verdict === 'wrong'
                      ? 'border-wrong focus:border-wrong focus:ring-wrong/25'
                      : ''
                }
              />
            </label>
          )
        })}
      </div>

      {!committed && (
        <Button
          size="full"
          variant="accent"
          type="submit"
          disabled={locked || filled.length === 0}
        >
          {filled.length === 0
            ? 'Fill in what you know'
            : `Lock in ${filled.length} of ${question.answer_fields.length}`}
          <Lock size={18} aria-hidden />
        </Button>
      )}
    </form>
  )
}
