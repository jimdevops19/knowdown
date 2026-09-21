import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QuestionCatalogCard } from './QuestionCard'
import { AnswerKeyPanel } from './AnswerKeyPanel'
import type { PlayQuestion, TesterQuestionCard, TesterVerdict } from '../../lib/api/types'

/*
 * What is checked here is the two places the tester deliberately differs from
 * the player-facing app. Everything else it does is other components' behaviour
 * — the board is `QuestionBoard`, the clock is `useQuestionClock`, the reveal is
 * `describeAnswerKey` — and re-testing those here would be testing the imports.
 *
 *  1. **A card publishes what a play-time payload may not**: the slug, and
 *     whether matchmaking can draw the question at all. Those two facts are the
 *     reason the catalog exists, so they are worth a test that fails if they
 *     quietly stop being rendered.
 *  2. **A reveal that the box score hides behind a button is shown flat here.**
 *     `describeAnswerKey` answers `inline` or `modal` by a rule about fitting in
 *     a *table row*; this page has no table, so a `modal` reveal is rendered in
 *     place. A regression to the button would put a click between a maintainer
 *     and the thing they navigated to see.
 */

const CARD: TesterQuestionCard = {
  id: 'q-1',
  type: 'single-answer',
  slug: 'kobe-81-point-game',
  description: 'Which team did Kobe score 81 against?',
  level: 5,
  category: 'nba',
  category_name: 'NBA',
  tags: { era: '2000s' },
  is_active: true,
  time_limit_seconds: 12,
  image: null,
  created_at: '2026-01-01T00:00:00Z',
}

function renderCard(question: TesterQuestionCard) {
  return render(
    <MemoryRouter>
      <QuestionCatalogCard question={question} typeLabel="Single answer" />
    </MemoryRouter>,
  )
}

describe('the catalog card', () => {
  it('names the question by its slug, which no player payload carries', () => {
    renderCard(CARD)

    expect(screen.getByText('kobe-81-point-game')).toBeInTheDocument()
  })

  it('links into the rehearsal by the (type, id) pair', () => {
    renderCard(CARD)

    expect(screen.getByRole('link')).toHaveAttribute('href', '/tester/single-answer/q-1')
  })

  it('marks a question matchmaking will never draw', () => {
    renderCard({ ...CARD, is_active: false })

    expect(screen.getByText('Inactive')).toBeInTheDocument()
  })

  it('says nothing about being inactive when it is not', () => {
    renderCard(CARD)

    expect(screen.queryByText('Inactive')).not.toBeInTheDocument()
  })
})

const ORDERING_QUESTION: PlayQuestion = {
  id: 'q-2',
  type: 'ordering',
  description: 'Put these title runs in order.',
  level: 6,
  category: 'nba',
  image: null,
  pre_question_info: '',
  instruction: 'Earliest first.',
  options: [
    { id: 2, text: '1996' },
    { id: 1, text: '1991' },
  ],
}

describe('the answer key panel', () => {
  it('renders a reveal the box score would have put behind a button', () => {
    /* An ordering key is a `modal` reveal — an arrangement does not fit a table
     * cell. Here the arrangement itself must be on screen with no interaction. */
    render(
      <AnswerKeyPanel
        question={ORDERING_QUESTION}
        answerKey={{ type: 'ordering', option_ids: [1, 2] }}
        verdict={null}
        peeked
      />,
    )

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText('1991')).toBeInTheDocument()
    expect(screen.getByText('1996')).toBeInTheDocument()
  })

  it('says when the answer was revealed rather than earned', () => {
    render(
      <AnswerKeyPanel
        question={ORDERING_QUESTION}
        answerKey={{ type: 'ordering', option_ids: [1, 2] }}
        verdict={null}
        peeked
      />,
    )

    expect(screen.getByText(/Revealed without answering/)).toBeInTheDocument()
  })

  it('stays quiet about that when the question was actually played', () => {
    const verdict: TesterVerdict = {
      is_correct: true,
      score: 1,
      points: 90,
      elapsed_ms: 1200,
      time_limit_ms: 12_000,
      submitted: { type: 'ordering', option_ids: [1, 2] },
      answer_key: { type: 'ordering', option_ids: [1, 2] },
    }

    render(
      <AnswerKeyPanel
        question={ORDERING_QUESTION}
        answerKey={verdict.answer_key}
        verdict={verdict}
        peeked={false}
      />,
    )

    expect(screen.queryByText(/Revealed without answering/)).not.toBeInTheDocument()
  })
})
