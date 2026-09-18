import type { ReactNode } from 'react'
import { AnswerList } from '../../../components/AnswerList'
import { AnswerPoolList } from '../../../components/AnswerPoolList'
import type {
  AnswerKey,
  ImageOption,
  MatrixQuestion,
  PlayQuestion,
  PlayerAnswerRecord,
  TextOption,
} from '../../../lib/api/types'

/*
 * How each question type says what the right answer was.
 *
 * One entry per type, the way the backend has one model, one schema, one
 * evaluator, one play-time serializer and one reveal builder per type — this is
 * the client's end of that last one, and it is a registry for the same reason:
 * a type that can be *played* and not *explained* should be a gap somebody can
 * see, not a box score that renders blank.
 *
 * ## The rule for inline vs. behind a button
 *
 * **An answer that is one short string or a boolean goes straight into the
 * table**, beside the two players' rows, because that is where the eye already
 * is and a button to reveal four characters is a button for its own sake.
 * Everything else — a set, an arrangement, a grid, a picture — **goes behind a
 * button into a modal**, because it does not fit a table cell and squeezing it
 * in costs the row its shape.
 *
 * Note the rule is about the *answer*, not the type, and the builders below
 * apply it per question: a free-text question with a single accepted spelling
 * reveals inline, and the same question authored with six spellings reveals as
 * a pool. Keying the choice to the type instead would mean picking the worse
 * layout for one of those two cases forever.
 */
export type Reveal =
  | { kind: 'inline'; content: ReactNode }
  | { kind: 'modal'; label: string; title: string; description?: string; body: ReactNode }

/** Whether to mark the first entry of a pool as this player's own.
 *
 *  The server floats a correct answer to the front, so "was this player right"
 *  is the whole question — and it is asked of the *record*, not inferred from
 *  the pool, because a wrong answer that happens to sort first would otherwise
 *  be decorated as theirs. A partly-right grid (`score > 0, is_correct false`)
 *  is handled per cell rather than here; see `matrixReveal`. */
const answeredCorrectly = (mine: PlayerAnswerRecord | null) => !!mine?.is_correct

function optionText(options: TextOption[], id: number): string {
  // A board and its key come from the same question in the same response, so a
  // missing id is a contract break rather than a stale cache. Rendered as the
  // raw id instead of crashing the page: a box score with one odd-looking row
  // is a better failure than a blank screen, and the id is what a bug report
  // needs anyway.
  return options.find((option) => option.id === id)?.text ?? `#${id}`
}

function imageOption(options: ImageOption[], id: number): ImageOption | undefined {
  return options.find((option) => option.id === id)
}

/** The label a grid's row/column ids read back as. */
function axisTitles(question: MatrixQuestion) {
  return {
    rows: new Map(question.rows.map((row) => [row.id, row.title])),
    columns: new Map(question.columns.map((column) => [column.id, column.title])),
  }
}

/*
 * `describeAnswerKey` is the seam the table calls. It takes the board as well
 * as the key because most of the key is *ids* — the reveal names options the
 * way a submission does, so turning them back into words needs the board they
 * were drawn from.
 */
export function describeAnswerKey({
  question,
  answerKey,
  mine,
}: {
  question: PlayQuestion
  answerKey: AnswerKey
  /** This player's own record, or null if the clock beat them. Used only to
   *  decide whether their answer is marked inside a pool. */
  mine: PlayerAnswerRecord | null
}): Reveal {
  switch (answerKey.type) {
    case 'true-false':
      return { kind: 'inline', content: answerKey.answer ? 'True' : 'False' }

    case 'single-answer': {
      if (question.type !== 'single-answer') return brokenPair()
      const [id] = answerKey.option_ids
      return { kind: 'inline', content: optionText(question.options, id) }
    }

    case 'image-answer': {
      if (question.type !== 'image-answer') return brokenPair()
      const [id] = answerKey.option_ids
      const option = imageOption(question.options, id)
      // One right answer, and still a modal: the answer *is* a picture, and a
      // thumbnail shrunk into a table row is neither a legible answer nor a
      // legible row. The label rides along as the button text, so the table
      // still says something without being opened.
      return {
        kind: 'modal',
        label: option?.label || 'See the answer',
        title: 'The answer',
        body: option ? (
          <figure className="flex flex-col gap-2">
            <img
              src={option.image}
              alt={option.label}
              className="w-full rounded-tile border border-correct/40"
            />
            <figcaption className="text-sm text-chalk">{option.label}</figcaption>
          </figure>
        ) : (
          <p className="text-sm text-ash">This option is no longer available.</p>
        ),
      }
    }

    case 'multiple-answer': {
      if (question.type !== 'multiple-answer') return brokenPair()
      const answers = answerKey.option_ids.map((id) => optionText(question.options, id))
      return {
        kind: 'modal',
        label: `${answers.length} correct`,
        title: 'The correct set',
        // Worth saying out loud: the board never told the player how many to
        // tick, and the count only becomes knowable here.
        description: `All ${answers.length} had to be ticked, and nothing else.`,
        // A plain list, not an `AnswerPoolList`: there is no truncation here
        // and nothing withheld, so wrapping it in a pool would mean inventing a
        // `total` equal to the length — a "… and 0 more" waiting to happen.
        body: <AnswerList items={answers} />,
      }
    }

    case 'ordering': {
      if (question.type !== 'ordering') return brokenPair()
      return {
        kind: 'modal',
        label: 'See the order',
        title: 'The right order',
        description: question.instruction,
        body: (
          <ol className="flex flex-col gap-1.5">
            {answerKey.option_ids.map((id, index) => (
              <li
                key={id}
                className="flex items-center gap-3 rounded-tile border border-chalk/8 bg-panel/60 px-3 py-2 text-sm text-chalk"
              >
                <span className="nums font-display text-xs font-bold text-ash">
                  {index + 1}
                </span>
                {optionText(question.options, id)}
              </li>
            ))}
          </ol>
        ),
      }
    }

    case 'free-text': {
      // The per-question half of the rule at the top: one accepted spelling is
      // one short string and belongs in the row.
      if (answerKey.total === 1) {
        return { kind: 'inline', content: answerKey.accepted[0] }
      }
      return {
        kind: 'modal',
        label: `${answerKey.total} accepted`,
        title: 'What would have counted',
        description: 'Any one of these was a correct answer.',
        body: (
          <AnswerPoolList pool={answerKey} leading={answeredCorrectly(mine)} />
        ),
      }
    }

    case 'matrix': {
      if (question.type !== 'matrix') return brokenPair()
      return matrixReveal(question, answerKey, mine)
    }

    case 'gradual-hints': {
      if (question.type !== 'gradual-hints') return brokenPair()
      return {
        kind: 'modal',
        label: 'See the answer',
        title: 'The answer, and the clues',
        body: (
          <div className="flex flex-col gap-4">
            {answerKey.answer_fields.map((field) => (
              <section key={field.field_id} className="flex flex-col gap-1.5">
                <h3 className="font-display text-xs font-bold uppercase tracking-wider text-ash">
                  {field.label}
                </h3>
                <AnswerPoolList pool={field} leading={answeredCorrectly(mine)} />
              </section>
            ))}
            {answerKey.hints.length > 0 && (
              <section className="flex flex-col gap-1.5 border-t border-chalk/8 pt-4">
                <h3 className="font-display text-xs font-bold uppercase tracking-wider text-ash">
                  The clues, in order
                </h3>
                <ol className="flex flex-col gap-1.5">
                  {answerKey.hints.map((hint, index) => (
                    <li
                      key={hint}
                      className="flex gap-3 rounded-tile border border-chalk/8 bg-panel/60 px-3 py-2 text-sm text-chalk"
                    >
                      <span className="nums font-display text-xs font-bold text-ash">
                        {index + 1}
                      </span>
                      {hint}
                    </li>
                  ))}
                </ol>
              </section>
            )}
          </div>
        ),
      }
    }
  }
}

/*
 * A grid, one section per intersection the question actually asked about.
 *
 * The sparse squares are absent here exactly as they were absent from the
 * board: a cell nobody was asked to fill has no answer being withheld, and
 * drawing an empty one would invent a question that was never put.
 *
 * Marking is **per cell**, not per question, which is the difference between
 * this and every other type: a grid is several independent claims, so a player
 * who filled three of five in correctly is right in three places and wrong in
 * two. `is_correct` on the record is false for them — it means *the whole
 * grid* — so using it to mark would tell somebody who got three right that they
 * got nothing right. What each cell checks instead is what this player typed
 * into that cell, against the pool the server floated it to the front of.
 */
function matrixReveal(
  question: MatrixQuestion,
  answerKey: Extract<AnswerKey, { type: 'matrix' }>,
  mine: PlayerAnswerRecord | null,
): Reveal {
  const { rows, columns } = axisTitles(question)
  const typed = new Map<string, string>()
  if (mine?.submitted.type === 'matrix') {
    for (const cell of mine.submitted.cells) {
      typed.set(`${cell.row_id}:${cell.column_id}`, cell.answer)
    }
  }

  return {
    kind: 'modal',
    label: `${answerKey.cells.length} squares`,
    title: 'The grid, filled in',
    description: 'Any one of the answers listed takes its square.',
    body: (
      <div className="flex flex-col gap-4">
        {answerKey.cells.map((cell) => {
          const answer = typed.get(`${cell.row_id}:${cell.column_id}`)
          // Folded the way the backend folds it (`apps.questions.matching`), so
          // a player who typed `lebron james` is marked right here for the same
          // reason they were scored right there.
          const got =
            !!answer &&
            cell.accepted.some(
              (accepted) => accepted.trim().toLowerCase() === answer.trim().toLowerCase(),
            )
          return (
            <section key={`${cell.row_id}:${cell.column_id}`} className="flex flex-col gap-1.5">
              <h3 className="font-display text-xs font-bold uppercase tracking-wider text-ash">
                {rows.get(cell.row_id) ?? cell.row_id} ×{' '}
                {columns.get(cell.column_id) ?? cell.column_id}
              </h3>
              <AnswerPoolList pool={cell} leading={got} />
            </section>
          )
        })}
      </div>
    ),
  }
}

/* A key whose `type` disagrees with the board it arrived beside. The two come
 * from one question in one response, so this is unreachable short of a backend
 * bug — and it renders as a sentence rather than throwing, because one broken
 * row should not take the rest of the box score down with it. */
function brokenPair(): Reveal {
  return { kind: 'inline', content: '—' }
}
