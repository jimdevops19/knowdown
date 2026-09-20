import { useState } from 'react'
import type { MultipleAnswerQuestion } from '../../../lib/api/types'
import { AnswerTile, type TileState } from '../AnswerTile'
import { Button } from '../../../components/Button'
import { OPTION_GRID, OPTION_LETTERS, type BoardProps } from './types'
import { useAutoSubmitAtDeadline } from './useAutoSubmitAtDeadline'

/*
 * Tick every option that is right — and the board does not say how many that
 * is, because the payload doesn't carry a count and deliberately never will: on
 * a four-option question, "two of these are correct" halves the search space.
 *
 * So this is the one board with a **confirm step**, and the reason is structural
 * rather than cautious: a single-answer tap is unambiguously a complete answer,
 * while a tick is not — the player is still deciding whether there is another
 * one. Submitting on each tick would send an answer nobody finished. The
 * commit is therefore explicit, and the button says how many are selected so
 * the decision being confirmed is visible.
 *
 * Scoring is partial: the server credits the correct ticks and charges the
 * wrong ones, `(right - wrong) / correct` floored at zero
 * (`apps.questions.services.evaluation`). So two of three right is worth two
 * thirds, and ticking everything is still worth nothing.
 *
 * Which is why the ticks are also sent **at the wire** if the player never
 * presses the button: partial work that was never submitted is the one way to
 * score zero on a question you mostly knew, and the clock should not be able to
 * do that to somebody who is still deciding on their last tick. An empty set is
 * still never sent — the server refuses it as malformed, and it is worth what
 * silence is worth anyway.
 */
export function MultipleAnswerBoard({
  question,
  submission,
  verdict,
  deadlineAt,
  locked,
  onAnswer,
}: BoardProps<MultipleAnswerQuestion>) {
  const [selected, setSelected] = useState<number[]>([])

  const committed = submission?.type === 'multiple-answer' ? submission.option_ids : null
  const shown = committed ?? selected

  useAutoSubmitAtDeadline({
    deadlineAt,
    committed: committed !== null,
    locked,
    build: () =>
      shown.length === 0 ? null : { type: 'multiple-answer' as const, option_ids: shown },
    onAnswer,
  })

  const toggle = (optionId: number) =>
    setSelected((current) =>
      current.includes(optionId)
        ? current.filter((id) => id !== optionId)
        : [...current, optionId],
    )

  return (
    <div className="flex flex-col gap-3">
      <div className={OPTION_GRID}>
        {question.options.map((option, index) => {
          const picked = shown.includes(option.id)
          // The verdict lands on the *set*, not on each option — the server
          // says "your answer was right", never "this one was". So every
          // selected tile takes the same verdict colour, and the unselected
          // ones dim: painting them individually would be inventing a per-option
          // answer key the API never sent.
          const state: TileState = picked
            ? (verdict ?? 'picked')
            : locked
              ? 'dimmed'
              : 'idle'
          return (
            <AnswerTile
              key={option.id}
              state={state}
              lead={OPTION_LETTERS[index] ?? index + 1}
            lane={index}
              disabled={locked}
              onClick={() => toggle(option.id)}
            >
              {option.text}
            </AnswerTile>
          )
        })}
      </div>

      {!committed && (
        <Button
          size="full"
          variant="accent"
          // An empty set is not a submission — the server rejects it as
          // malformed rather than scoring it zero, so the button refuses first.
          disabled={locked || selected.length === 0}
          onClick={() => onAnswer({ type: 'multiple-answer', option_ids: selected })}
        >
          {selected.length === 0
            ? 'Select your answers'
            : `Lock in ${selected.length} answer${selected.length === 1 ? '' : 's'}`}
        </Button>
      )}
    </div>
  )
}
