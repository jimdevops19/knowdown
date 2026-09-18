import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { RevealCell } from './RevealCell'
import { describeAnswerKey } from './reveals'
import { describeSubmission } from './submissions'
import type { ReactNode } from 'react'
import type {
  AnswerKey,
  MatrixQuestion,
  NameAsManyQuestion,
  MultipleAnswerQuestion,
  PlayQuestion,
  PlayerAnswerRecord,
  SingleAnswerQuestion,
  TrueFalseQuestion,
} from '../../../lib/api/types'

/*
 * What this file is about is the *rule*, not the markup.
 *
 * A box score reveals an answer in one of two ways — in the table cell, or
 * behind a button — and which one is a decision made per question by
 * `describeAnswerKey`. That decision is the whole design (see the rule at the
 * top of `reveals.tsx`), so it is what gets asserted: the `kind` of the reveal,
 * not the classes it renders with.
 *
 * The one piece of DOM worth checking is the truncation tail, because it is the
 * only place the UI makes a claim about data it does not have.
 */

const record = (submitted: PlayerAnswerRecord['submitted'], is_correct = true): PlayerAnswerRecord => ({
  submitted,
  is_correct,
  score: is_correct ? 1 : 0,
  points: is_correct ? 10 : 0,
  response_time_ms: 2000,
  answered_at: '2026-01-01T00:00:00Z',
})

const base = { id: 'q1', description: 'Who?', level: 5, category: 'nba', image: null }

const singleAnswer: SingleAnswerQuestion = {
  ...base,
  type: 'single-answer',
  options: [
    { id: 1, text: 'Kobe Bryant' },
    { id: 2, text: "Shaquille O'Neal" },
  ],
}

const trueFalse: TrueFalseQuestion = { ...base, type: 'true-false' }

const multipleAnswer: MultipleAnswerQuestion = {
  ...base,
  type: 'multiple-answer',
  options: [
    { id: 1, text: 'Kobe Bryant' },
    { id: 2, text: "Shaquille O'Neal" },
    { id: 3, text: 'Derek Fisher' },
  ],
}

const matrix: MatrixQuestion = {
  ...base,
  type: 'matrix',
  row_count: 1,
  column_count: 1,
  rows: [{ id: 10, title: 'Chicago Bulls' }],
  columns: [{ id: 20, title: 'Washington Wizards' }],
  cells: [{ row_id: 10, column_id: 20 }],
}

const nameAsMany: NameAsManyQuestion = {
  ...base,
  type: 'name-as-many',
  target_score: 10,
  dataset: 'nba-career-stats',
  max_names: 200,
}

function reveal(question: PlayQuestion, answerKey: AnswerKey, mine: PlayerAnswerRecord | null = null) {
  return describeAnswerKey({ question, answerKey, mine })
}

describe('which answers go inline and which go behind a button', () => {
  it('puts a single correct option straight in the row', () => {
    const result = reveal(singleAnswer, { type: 'single-answer', option_ids: [1] })

    expect(result.kind).toBe('inline')
    expect(result).toMatchObject({ content: 'Kobe Bryant' })
  })

  it('puts a boolean straight in the row', () => {
    expect(reveal(trueFalse, { type: 'true-false', answer: false })).toMatchObject({
      kind: 'inline',
      content: 'False',
    })
  })

  it('puts a set behind a button, and the button says how many', () => {
    const result = reveal(multipleAnswer, {
      type: 'multiple-answer',
      option_ids: [1, 3],
    })

    expect(result).toMatchObject({ kind: 'modal', label: '2 correct' })
  })

  it('decides per question, not per type', () => {
    /* A free-text question with one accepted spelling is one short string and
     * belongs in the row; the same type authored with six is a pool. Keying the
     * layout to the type would pick the wrong one of these forever. */
    const alone = reveal(
      { ...base, type: 'free-text' },
      { type: 'free-text', accepted: ['Kobe Bryant'], total: 1 },
    )
    const many = reveal(
      { ...base, type: 'free-text' },
      {
        type: 'free-text',
        accepted: ['Kobe Bryant', 'Kobe', 'Bryant', 'Mamba', 'KB24'],
        total: 6,
      },
    )

    expect(alone.kind).toBe('inline')
    expect(many.kind).toBe('modal')
  })
})

describe('the truncated tail', () => {
  const answerKey: AnswerKey = {
    type: 'matrix',
    cells: [
      {
        row_id: 10,
        column_id: 20,
        accepted: ['Michael Jordan', 'Ron Harper', 'Jerry Stackhouse', 'Kwame Brown', 'Tyson Chandler'],
        total: 22,
      },
    ],
  }

  it('reports the answers it was never sent as a count', () => {
    const result = reveal(matrix, answerKey)
    if (result.kind !== 'modal') throw new Error('a grid reveals behind a button')

    render(<>{result.body}</>)

    expect(screen.getByText(/and 17 more accepted answers/)).toBeInTheDocument()
  })

  it('marks the square this player got right, and only that one', () => {
    /* Per cell, not per question: a grid is several independent claims, so the
     * record's `is_correct` — which means the *whole* grid — would tell somebody
     * who filled three of five in correctly that they got nothing right. */
    const mine = record(
      { type: 'matrix', cells: [{ row_id: 10, column_id: 20, answer: 'michael jordan' }] },
      false,
    )

    const result = reveal(matrix, answerKey, mine)
    if (result.kind !== 'modal') throw new Error('a grid reveals behind a button')
    render(<>{result.body}</>)

    expect(screen.getByText('your answer')).toBeInTheDocument()
  })
})

describe('a list of names reads back as what each one paid', () => {
  const key: AnswerKey = {
    type: 'name-as-many',
    target_score: 10,
    earned: 5,
    named: [
      { name: 'Stephen Curry', points: 2 },
      { name: 'Nobody Atall', points: 0 },
      { name: 'Kyle Korver', points: 3 },
    ],
    accepted: ['Ray Allen', 'Reggie Miller'],
    total: 180,
  }

  it('says what was collected on the button, since the number is the story', () => {
    expect(reveal(nameAsMany, key)).toMatchObject({
      kind: 'modal',
      label: '5 of 10 pts',
    })
  })

  it('prices every name they gave, including the one that counted for nothing', () => {
    render(<>{(reveal(nameAsMany, key) as { body: ReactNode }).body}</>)

    expect(screen.getByText('+2')).toBeInTheDocument()
    expect(screen.getByText('+3')).toBeInTheDocument()
    // A miss is shown as a miss rather than dropped: a single credit figure
    // cannot say which of three names was the one that did not count.
    expect(screen.getByText('Nobody Atall')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
  })

  it('reports the names it was never sent as a count', () => {
    render(<>{(reveal(nameAsMany, key) as { body: ReactNode }).body}</>)

    expect(screen.getByText(/178 more/)).toBeInTheDocument()
  })

  it('lists the names they gave under their own row, unpriced', () => {
    // The submission renderer says what was *sent*; pricing is the answer
    // key's job, one column over.
    expect(
      describeSubmission({
        question: nameAsMany,
        submitted: { type: 'name-as-many', names: ['Stephen Curry', 'Kyle Korver'] },
      }),
    ).toMatchObject({ kind: 'modal', label: '2 named' })
  })
})

describe('a player row says what they actually put', () => {
  it('shows the option they picked, not just the verdict', () => {
    const result = describeSubmission({
      question: singleAnswer,
      submitted: { type: 'single-answer', option_id: 2 },
    })

    expect(result).toMatchObject({ kind: 'inline', content: "Shaquille O'Neal" })
  })

  it('shows what they typed verbatim', () => {
    const result = describeSubmission({
      question: { ...base, type: 'free-text' },
      submitted: { type: 'free-text', text: 'kobe' },
    })

    expect(result).toMatchObject({ kind: 'inline', content: '“kobe”' })
  })

  it('puts a multi-part submission behind a button', () => {
    const result = describeSubmission({
      question: multipleAnswer,
      submitted: { type: 'multiple-answer', option_ids: [1, 2] },
    })

    expect(result).toMatchObject({ kind: 'modal', label: '2 picked' })
  })
})

describe('RevealCell', () => {
  it('opens and closes the modal a button-shaped reveal sits behind', () => {
    const result = reveal(multipleAnswer, { type: 'multiple-answer', option_ids: [1, 3] })

    render(<RevealCell reveal={result} tone="text-gold" />)

    expect(screen.queryByText('The correct set')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /2 correct/ }))
    expect(screen.getByText('The correct set')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByText('The correct set')).not.toBeInTheDocument()
  })
})
