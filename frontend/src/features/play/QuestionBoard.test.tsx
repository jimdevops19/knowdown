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
  pre_question_info: '',
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

/** A press and a release that never moved — the ordering board's quick path,
 *  and the half of its gesture handling that is not a drag. It listens on
 *  pointer events rather than `click`, so `fireEvent.click` alone does nothing
 *  to it. */
function tap(element: Element) {
  fireEvent.pointerDown(element, { pointerId: 1, clientX: 10, clientY: 10, button: 0 })
  fireEvent.pointerUp(element, { pointerId: 1, clientX: 10, clientY: 10 })
}

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

  it('asks a number field for a keypad, and gives every box the same column', () => {
    // `kind` decides the *keyboard* and the length cap, and no longer the
    // width. Sizing each box to its kind laid "Year / Round / Game number" out
    // on a phone as a stub, a box running to the right edge, and a third
    // stranded full-width on its own line — so the boxes are a grid now, one
    // equal column each, and `inputMode` is the half of `kind` a phone player
    // actually feels.
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
    // Neither box carries a width of its own — the grid above them does, and
    // both sit in the same track whatever their kind.
    const yearLabel = year.closest('label')
    const roundLabel = round.closest('label')
    expect(yearLabel?.className).toBe(roundLabel?.className)
    expect(yearLabel?.parentElement?.className).toContain('grid-cols-2')
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

  it('sends the ticks of an unfinished multiple-answer at the whistle', async () => {
    // The partial-credit half of the same rule: the server now pays
    // `(right - wrong) / correct`, so ticks nobody pressed the button on are
    // worth real points — and a player still deciding on their last tick must
    // not lose the two they were sure of to the clock.
    vi.useFakeTimers()
    try {
      const submissions: unknown[] = []
      const { getByText } = render(
        <QuestionBoard
          question={QUESTION_FIXTURES['multiple-answer']}
          hints={[]}
          submission={null}
          verdict={null}
          locked={false}
          deadlineAt={Date.now() + 10_000}
          onAnswer={(submission) => submissions.push(submission)}
          revealOptions
        />,
      )

      fireEvent.click(getByText('Trae Young'))

      expect(submissions).toEqual([])
      act(() => {
        vi.advanceTimersByTime(10_000)
      })
      expect(submissions).toEqual([{ type: 'multiple-answer', option_ids: [2] }])
    } finally {
      vi.useRealTimers()
    }
  })

  it('sends nothing at the whistle when no option was ticked', () => {
    // An empty set is malformed rather than a zero — the server refuses it, so
    // the board must not send one. Silence costs the player exactly the same.
    vi.useFakeTimers()
    try {
      const submissions: unknown[] = []
      render(
        <QuestionBoard
          question={QUESTION_FIXTURES['multiple-answer']}
          hints={[]}
          submission={null}
          verdict={null}
          locked={false}
          deadlineAt={Date.now() + 10_000}
          onAnswer={(submission) => submissions.push(submission)}
          revealOptions
        />,
      )

      act(() => {
        vi.advanceTimersByTime(10_000)
      })
      expect(submissions).toEqual([])
    } finally {
      vi.useRealTimers()
    }
  })

  it('says the question is an ordering one before any option is on screen', () => {
    // The whole reason the call-out lives on `QuestionBoard` rather than on the
    // board: during the read delay there are no tiles yet, and that is exactly
    // the beat in which a player has to learn that this question is answered by
    // arranging rather than by picking.
    const { container } = render(
      <QuestionBoard
        question={QUESTION_FIXTURES.ordering}
        hints={[]}
        submission={null}
        verdict={null}
        locked={false}
        deadlineAt={null}
        onAnswer={() => {}}
        revealOptions={false}
      />,
    )

    expect(container.textContent).toContain('tap the options in order')
    expect(container.textContent).toContain('Most points first')
    // Still the read delay: the instruction is up, the options are not.
    expect(container.textContent).not.toContain('LeBron James')
  })

  it('draws a numbered slot per position and fills them by tapping a card', () => {
    // The board's whole shape: N empty, numbered slots from the start, the
    // options loose in a pool, and a tap — the fast gesture, next to the drag —
    // moving a card between the two.
    const { getByRole, getByLabelText, queryByLabelText } = render(
      <QuestionBoard
        question={QUESTION_FIXTURES.ordering}
        hints={[]}
        submission={null}
        verdict={null}
        locked={false}
        deadlineAt={null}
        onAnswer={() => {}}
        revealOptions
      />,
    )

    expect(getByLabelText('Position 1, empty')).toBeTruthy()
    expect(getByLabelText('Position 2, empty')).toBeTruthy()
    // The button names the slot still open, not just a count.
    expect(getByRole('button', { name: 'Fill the 1st slot' })).toBeTruthy()

    tap(getByLabelText('Trae Young. Activate to put it in position 1'))
    expect(getByLabelText('Position 1: Trae Young. Activate to take it out')).toBeTruthy()
    expect(getByRole('button', { name: 'Fill the 2nd slot' })).toBeTruthy()

    // And a tap on a filled slot sends the card back to the pool.
    tap(getByLabelText('Position 1: Trae Young. Activate to take it out'))
    expect(queryByLabelText('Position 1: Trae Young. Activate to take it out')).toBeNull()
    expect(getByLabelText('Position 1, empty')).toBeTruthy()
  })

  it('drops a dragged card into the slot it was released over', () => {
    // The gesture the layout promises. It is pointer-events rather than HTML5
    // drag-and-drop because `dragstart` never fires on touch — on a phone-first
    // game the native version would be a desktop-only feature — so this walks
    // the real sequence: down on the card, move across, up over slot 2.
    const { container, getByLabelText } = render(
      <QuestionBoard
        question={QUESTION_FIXTURES.ordering}
        hints={[]}
        submission={null}
        verdict={null}
        locked={false}
        deadlineAt={null}
        onAnswer={() => {}}
        revealOptions
      />,
    )

    // jsdom lays nothing out, so the slots are given the geometry the drop is
    // resolved against — the board reads these rects live, at drop time.
    const rows = container.querySelectorAll('ol > li')
    rows.forEach((row, index) => {
      row.getBoundingClientRect = () =>
        ({ left: 0, right: 300, top: index * 50, bottom: index * 50 + 44 }) as DOMRect
    })

    const card = getByLabelText('Trae Young. Activate to put it in position 1')
    fireEvent.pointerDown(card, { pointerId: 2, clientX: 10, clientY: 200, button: 0 })
    fireEvent.pointerMove(card, { pointerId: 2, clientX: 100, clientY: 60 })
    fireEvent.pointerUp(card, { pointerId: 2, clientX: 100, clientY: 60 })

    // Position 2, not position 1: a drag goes where it was dropped, while a
    // tap takes the first free slot.
    expect(getByLabelText('Position 2: Trae Young. Activate to take it out')).toBeTruthy()
    expect(getByLabelText('Position 1, empty')).toBeTruthy()
  })

  it('submits the sequence in the order the cards were placed', () => {
    const submissions: unknown[] = []
    const { getByRole, getByLabelText } = render(
      <QuestionBoard
        question={QUESTION_FIXTURES.ordering}
        hints={[]}
        submission={null}
        verdict={null}
        locked={false}
        deadlineAt={null}
        onAnswer={(submission) => submissions.push(submission)}
        revealOptions
      />,
    )

    tap(getByLabelText('Trae Young. Activate to put it in position 1'))
    tap(getByLabelText('LeBron James. Activate to put it in position 2'))
    fireEvent.click(getByRole('button', { name: 'Lock in this order' }))

    expect(submissions).toEqual([{ type: 'ordering', option_ids: [2, 1] }])
  })
})
