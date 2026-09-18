import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render } from '@testing-library/react'
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
  // A hint is not an answer, and it is on this list for the same reason the
  // backend puts it in `FORBIDDEN_FIELD_NAMES`: it is the part of a
  // gradual-hints question that has to arrive *late*, so a board that rendered
  // one off the question payload would have defeated the whole type.
  hints: ['POISON-HINT'],
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
  'gradual-hints': {
    ...BASE,
    type: 'gradual-hints',
    hint_count: 3,
    hint_interval_ms: 5000,
    // One of each kind: the board sizes a number box differently from a text
    // one, so a fixture with only one kind would render half of it.
    answer_fields: [
      { id: 1, label: 'Year', kind: 'number', ...POISON },
      { id: 2, label: 'Round', kind: 'text', ...POISON },
    ],
    ...POISON,
  },
  'name-as-many': {
    ...BASE,
    type: 'name-as-many',
    target_score: 24,
    dataset: 'nba-career-stats',
    max_names: 200,
    // The poison matters most on this one: its answer key is a list of
    // hundreds of names living in a baked CSV, so a board that rendered
    // whatever keys arrived would publish the whole thing.
    ...POISON,
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
        hints={[]}
        submission={null}
        verdict={null}
        locked={false}
        deadlineAt={null}
        onAnswer={() => {}}
        revealOptions
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
        // Empty: the clues are what the *socket* delivers, so a board handed a
        // poisoned question must render none of them. The board's own handling
        // of real, arrived clues is asserted below.
        hints={[]}
        submission={null}
        verdict={null}
        locked={false}
        deadlineAt={null}
        onAnswer={() => {}}
        revealOptions
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

  it('draws a slot for every clue and the text of only those that arrived', () => {
    // The board's one job that no other board has: a question whose content is
    // still being delivered has to look like one. Slots for all three from the
    // start (a board that grew a line every few seconds would shift the inputs
    // under the player's thumb), text for the one that has landed.
    const { container, getByText } = render(
      <QuestionBoard
        question={QUESTION_FIXTURES['gradual-hints']}
        hints={['The final score was 93-89']}
        submission={null}
        verdict={null}
        locked={false}
        deadlineAt={null}
        onAnswer={() => {}}
        revealOptions
      />,
    )

    expect(container.querySelectorAll('li')).toHaveLength(3)
    expect(getByText('The final score was 93-89')).toBeTruthy()
  })

  it('draws a number field short and a text field wide, and asks for a keypad', () => {
    // The board's only use for `kind`. A year box the width of a sentence is
    // the bug this exists to prevent, and `inputMode` is the half of it a
    // phone player actually feels.
    const { getByLabelText } = render(
      <QuestionBoard
        question={QUESTION_FIXTURES['gradual-hints']}
        hints={[]}
        submission={null}
        verdict={null}
        locked={false}
        deadlineAt={null}
        onAnswer={() => {}}
        revealOptions
      />,
    )

    const year = getByLabelText('Year')
    const round = getByLabelText('Round')

    expect(year.getAttribute('inputmode')).toBe('numeric')
    expect(round.getAttribute('inputmode')).toBeNull()
    // Width lives on the label that wraps the input, since the input itself is
    // always `w-full` of whatever it is given.
    expect(year.closest('label')?.className).toContain('w-28')
    expect(round.closest('label')?.className).toContain('flex-1')
    // Never the native number input: its spinners and scroll-to-change are a
    // wrong answer waiting for a mistap.
    expect(year.getAttribute('type')).not.toBe('number')
  })

  it('submits the boxes that were filled in, by id', () => {
    // Partial is a real answer here — the server credits per field — so the
    // payload is what was typed and not a padded set of empties.
    const submissions: unknown[] = []
    const { getByLabelText, getByRole } = render(
      <QuestionBoard
        question={QUESTION_FIXTURES['gradual-hints']}
        hints={[]}
        submission={null}
        verdict={null}
        locked={false}
        deadlineAt={null}
        onAnswer={(submission) => submissions.push(submission)}
        revealOptions
      />,
    )

    fireEvent.change(getByLabelText('Year'), { target: { value: '2016' } })
    fireEvent.click(getByRole('button', { name: /Lock in 1 of 2/ }))

    expect(submissions).toEqual([
      { type: 'gradual-hints', answer_fields: [{ field_id: 1, text: '2016' }] },
    ])
  })

  it('collects names into one payload, ignoring a repeat', () => {
    // The mode's whole shape in one case: names pile up locally, nothing is
    // graded on the way in, a repeat is absorbed rather than refused (the
    // server calls a repeated name malformed), and the list goes out once.
    const submissions: unknown[] = []
    const { getByLabelText, getByRole } = render(
      <QuestionBoard
        question={QUESTION_FIXTURES['name-as-many']}
        hints={[]}
        submission={null}
        verdict={null}
        locked={false}
        deadlineAt={null}
        onAnswer={(submission) => submissions.push(submission)}
        revealOptions
      />,
    )

    const field = getByLabelText('Add a name')
    const add = getByRole('button', { name: 'Add this name' })
    for (const name of ['Ray Allen', 'Vince Carter', '  ray   ALLEN ']) {
      fireEvent.change(field, { target: { value: name } })
      fireEvent.click(add)
    }

    fireEvent.click(getByRole('button', { name: /Lock in 2/ }))

    expect(submissions).toEqual([
      { type: 'name-as-many', names: ['Ray Allen', 'Vince Carter'] },
    ])
  })

  it('sends what it has before the server closes the question', async () => {
    // A player still typing at the whistle would otherwise score nothing at
    // all — the one way to lose this question that has nothing to do with
    // knowing any basketball.
    vi.useFakeTimers()
    try {
      const submissions: unknown[] = []
      const { getByLabelText, getByRole } = render(
        <QuestionBoard
          question={QUESTION_FIXTURES['name-as-many']}
          hints={[]}
          submission={null}
          verdict={null}
          locked={false}
          deadlineAt={Date.now() + 30_000}
          onAnswer={(submission) => submissions.push(submission)}
          revealOptions
        />,
      )

      fireEvent.change(getByLabelText('Add a name'), { target: { value: 'Ray Allen' } })
      fireEvent.click(getByRole('button', { name: 'Add this name' }))

      expect(submissions).toEqual([])
      act(() => {
        vi.advanceTimersByTime(30_000)
      })
      expect(submissions).toEqual([{ type: 'name-as-many', names: ['Ray Allen'] }])
    } finally {
      vi.useRealTimers()
    }
  })
})
