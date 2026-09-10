import type { SingleAnswerQuestion } from '../../../lib/api/types'
import { AnswerTile, type TileState } from '../AnswerTile'
import { OPTION_GRID, OPTION_LETTERS, type BoardProps } from './types'

/*
 * Pick one of the options. The default shape of a trivia question, and the one
 * everything else is a variation on.
 *
 * One tap submits — there is no "confirm". Under a ten-second clock a
 * confirmation step is a second tap that costs the player the race against
 * somebody who didn't have one, and there is nothing to protect them from: an
 * answer cannot be taken back either way, so the extra step would only make
 * that fact slower to reach.
 *
 * The options arrive **shuffled per matchup** — the same order for both
 * players, so the race is over the same board, and a different order in a later
 * match, so an option's position is not something to memorise. Nothing here
 * re-sorts them; doing so would break the first half of that.
 */
export function SingleAnswerBoard({
  question,
  submission,
  verdict,
  locked,
  onAnswer,
}: BoardProps<SingleAnswerQuestion>) {
  const pickedId =
    submission?.type === 'single-answer' || submission?.type === 'image-answer'
      ? submission.option_id
      : null

  return (
    <div className={OPTION_GRID}>
      {question.options.map((option, index) => {
        const picked = option.id === pickedId
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
            disabled={locked}
            onClick={() => onAnswer({ type: 'single-answer', option_id: option.id })}
          >
            {option.text}
          </AnswerTile>
        )
      })}
    </div>
  )
}
