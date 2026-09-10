import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { QuestionBoard } from './QuestionBoard'
import type { PlayQuestion, QuestionType } from '../../lib/api/types'

/*
 * Two things are checked here, and the second is the one that matters.
 *
 * 1. **Every question type has a board.** The backend keeps four registries in
 *    step — a model, a schema, an evaluator and a serializer per type — with a
 *    test that walks them so none can be the one that was forgotten. This is
 *    the fifth registry, and `QUESTION_FIXTURES` below is its walk: a type
 *    added to `lib/api/types.ts` with no fixture here fails to compile, and one
 *    with a fixture but no board fails this test.
 *
 * 2. **A board renders nothing that names an answer.** This is the client half
 *    of the backend's anti-cheat surface. Over there, a play-time serializer
 *    that declares `is_correct` or `answer` fails at import and the app refuses
 *    to boot; the payloads arriving here therefore contain no answer at all.
 *
 *    So this test does the paranoid thing: it feeds every board a payload that
 *    *has been poisoned* with the exact fields the server forbids, as though a
 *    regression on the other side had started sending them, and asserts none of
 *    it reaches the DOM. What it proves is that these boards render only the
 *    fields they explicitly name — no `{...option}` spread, no "render whatever
 *    keys came back" loop — so a leak upstream stays a leak upstream instead of
 *    becoming a leak on screen.
 */

/** The field names the backend's `FORBIDDEN_FIELD_NAMES` covers, with values
 *  distinctive enough that finding one in the DOM is unambiguous. */
const POISON = {
  answer: 'POISON-ANSWER',
  is_correct: 'POISON-IS-CORRECT',
  correct_position: 'POISON-CORRECT-POSITION',
  accepted_answers: ['POISON-ACCEPTED'],
  solution: 'POISON-SOLUTION',
  correct: 'POISON-CORRECT',
}

const BASE = {
  id: 'q-1',
  description: 'Who led the NBA in assists in 2019-20?',
  level: 5,
  category: 'nba',
  image: null,
}

const textOptions = [
  { id: 1, text: 'LeBron James', ...POISON },
  { id: 2, text: 'Trae Young', ...POISON },
]

/**
 * One fixture per question type. `Record<QuestionType, …>` is what makes this a
 * registry walk rather than a list somebody remembers to extend: a new type in
 * `QuestionType` is a compile error here until it has a fixture.
 */
const QUESTION_FIXTURES: Record<QuestionType, PlayQuestion> = {
  'single-answer': { ...BASE, type: 'single-answer', options: textOptions },
  'image-answer': {
    ...BASE,
    type: 'image-answer',
    options: [
      { id: 1, image: '/media/a.png', label: 'Kobe Bryant', ...POISON },
      { id: 2, image: '/media/b.png', label: 'Tim Duncan', ...POISON },
    ],
  },
  'multiple-answer': { ...BASE, type: 'multiple-answer', options: textOptions },
  'true-false': { ...BASE, type: 'true-false', ...POISON },
  'free-text': { ...BASE, type: 'free-text', ...POISON },
  ordering: {
    ...BASE,
    type: 'ordering',
    instruction: 'Most points first',
    options: textOptions,
  },
  matrix: {
    ...BASE,
    type: 'matrix',
    row_count: 2,
    column_count: 2,
    rows: [
      { id: 1, title: '2016', ...POISON },
      { id: 2, title: '2017', ...POISON },
    ],
    columns: [
      { id: 10, title: 'Champion', ...POISON },
      { id: 11, title: 'Finals MVP', ...POISON },
    ],
    // Sparse on purpose: three of the four intersections, so the board's
    // "not asked" rendering is exercised too.
    cells: [
      { row_id: 1, column_id: 10, ...POISON },
      { row_id: 1, column_id: 11, ...POISON },
      { row_id: 2, column_id: 10, ...POISON },
    ],
  },
  // The fixtures are deliberately poisoned with fields the real types don't
  // have, which is exactly what the cast is admitting to.
} as Record<QuestionType, PlayQuestion>

const TYPES = Object.keys(QUESTION_FIXTURES) as QuestionType[]

describe('QuestionBoard', () => {
  it.each(TYPES)('renders a board for %s', (type) => {
    const { container } = render(
      <QuestionBoard
        question={QUESTION_FIXTURES[type]}
        submission={null}
        verdict={null}
        locked={false}
        onAnswer={() => {}}
      />,
    )

    // The fallback the dispatcher renders for a type it doesn't know. Its
    // presence here would mean the registry has a hole.
    expect(container.textContent).not.toContain('needs a newer version')
    expect(container.textContent).toContain(BASE.description)
  })

  it.each(TYPES)('leaks no answer field for %s', (type) => {
    const { container } = render(
      <QuestionBoard
        question={QUESTION_FIXTURES[type]}
        submission={null}
        verdict={null}
        locked={false}
        onAnswer={() => {}}
      />,
    )

    // `innerHTML`, not `textContent`: an answer smuggled into a `title`, an
    // `alt`, a `value` or a `data-` attribute is just as readable in devtools
    // as one printed on the page, and would not show up in the text.
    const markup = container.innerHTML
    for (const poison of Object.values(POISON).flat()) {
      expect(markup).not.toContain(poison)
    }
  })
})
