import type {
  AnswerSubmission,
  MatrixQuestion,
  PlayQuestion,
  TextOption,
} from '../../../lib/api/types'
import { AnswerList } from '../../../components/AnswerList'
import type { Reveal } from './reveals'

/*
 * What a player actually said, in the same two shapes the answer key uses.
 *
 * The box score used to print only a verdict — "Correct", "Wrong", "60% right"
 * — which answers "did I win the question" and not "what did I put". For the
 * types where the answer is one tap that is nearly the same sentence; for a
 * grid it is not remotely, and "60% right" with no way to see *which* three
 * squares is a score with the post-mortem cut out of it.
 *
 * So a submission is described exactly the way a key is, by the same rule (one
 * short string inline, anything larger behind a button) and rendered by the
 * same `RevealCell`. The difference between the two is the tone they are drawn
 * in and the words at the top of the modal, which is as it should be: they are
 * the same kind of object, and only one of them is right.
 *
 * `null` is not "nothing to show" — it is the clock running out, which the
 * caller renders as its own thing. A submission that exists always describes to
 * something.
 */
export function describeSubmission({
  question,
  submitted,
}: {
  question: PlayQuestion
  submitted: AnswerSubmission
}): Reveal {
  switch (submitted.type) {
    case 'true-false':
      return { kind: 'inline', content: submitted.answer ? 'True' : 'False' }

    case 'single-answer': {
      if (question.type !== 'single-answer') return unknown()
      return { kind: 'inline', content: optionText(question.options, submitted.option_id) }
    }

    case 'image-answer': {
      if (question.type !== 'image-answer') return unknown()
      const option = question.options.find((entry) => entry.id === submitted.option_id)
      // A captionless "which player is this?" grid is a legitimate way to author
      // the question, and then there is no word for what they picked — the
      // picture is the only answer there is, so it goes in the modal.
      if (!option) return unknown()
      return {
        kind: 'modal',
        label: option.label || 'See the pick',
        title: 'What they picked',
        body: (
          <figure className="flex flex-col gap-2">
            <img
              src={option.image}
              alt={option.label}
              className="w-full rounded-tile border border-chalk/12"
            />
            <figcaption className="text-sm text-chalk">{option.label}</figcaption>
          </figure>
        ),
      }
    }

    case 'free-text':
      // Whatever they typed, verbatim — the backend stores the raw text for
      // exactly this, rather than the normalized key it compared.
      return { kind: 'inline', content: `“${submitted.text}”` }

    case 'multiple-answer': {
      if (question.type !== 'multiple-answer') return unknown()
      const picks = submitted.option_ids.map((id) => optionText(question.options, id))
      return {
        kind: 'modal',
        label: `${picks.length} picked`,
        title: 'What they ticked',
        body: <AnswerList items={picks} />,
      }
    }

    case 'ordering': {
      if (question.type !== 'ordering') return unknown()
      return {
        kind: 'modal',
        label: 'See their order',
        title: 'How they arranged it',
        description: question.instruction,
        body: (
          <ol className="flex flex-col gap-1.5">
            {submitted.option_ids.map((id, index) => (
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

    case 'matrix': {
      if (question.type !== 'matrix') return unknown()
      const { rows, columns } = axisTitles(question)
      // The squares they *left* are not listed. A blank is not an answer, and a
      // list of them would be a list of what somebody did not know — which the
      // score already says, more kindly, as a fraction.
      return {
        kind: 'modal',
        label: `${submitted.cells.length} filled`,
        title: 'What they filled in',
        body: (
          <AnswerList
            items={submitted.cells.map(
              (cell) =>
                `${rows.get(cell.row_id) ?? cell.row_id} × ${
                  columns.get(cell.column_id) ?? cell.column_id
                } — ${cell.answer}`,
            )}
          />
        ),
      }
    }

    case 'name-as-many': {
      if (question.type !== 'name-as-many') return unknown()
      // Which of them counted is the *answer key's* business, not this one —
      // a submission renderer says what was sent, and the key beside it says
      // what that was worth, name by name.
      return {
        kind: 'modal',
        label: `${submitted.names.length} named`,
        title: 'The names they gave',
        body: <AnswerList items={submitted.names} />,
      }
    }

    case 'gradual-hints': {
      if (question.type !== 'gradual-hints') return unknown()
      const labels = new Map(
        question.answer_fields.map((field) => [field.id, field.label]),
      )
      return {
        kind: 'modal',
        label: `${submitted.answer_fields.length} filled`,
        title: 'What they filled in',
        body: (
          <AnswerList
            items={submitted.answer_fields.map(
              (field) => `${labels.get(field.field_id) ?? field.field_id} — ${field.text}`,
            )}
          />
        ),
      }
    }
  }
}

function optionText(options: TextOption[], id: number): string {
  return options.find((option) => option.id === id)?.text ?? `#${id}`
}

function axisTitles(question: MatrixQuestion) {
  return {
    rows: new Map(question.rows.map((row) => [row.id, row.title])),
    columns: new Map(question.columns.map((column) => [column.id, column.title])),
  }
}

/* A submission whose `type` disagrees with the board it was played on. Both
 * come from one question in one response, so this is a backend bug rather than
 * a state the UI can reach — rendered rather than thrown for the reason the
 * answer key's twin is. */
function unknown(): Reveal {
  return { kind: 'inline', content: '—' }
}
