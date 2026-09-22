import { describe, expect, it } from 'vitest'
import { currentStreak, resultFor, summarisePlayerForm } from './playerForm'
import type { MatchupSummary } from '../../lib/api/types'

const ME = 'me'
const THEM = 'them'

function match(over: {
  me: { score?: number; correct?: number; timeMs?: number; won?: boolean }
  them?: { won?: boolean }
  questions?: number
  outcome?: 'played' | 'abandoned'
}): MatchupSummary {
  const { me, them = {}, questions = 5, outcome = 'played' } = over
  return {
    id: Math.random().toString(36).slice(2),
    category: 'nba',
    room: 'nba-all',
    question_count: questions,
    status: 'completed',
    outcome,
    is_ranked: true,
    started_at: '2026-09-01T10:00:00Z',
    completed_at: '2026-09-01T10:05:00Z',
    players: [
      {
        player: { id: ME, display_name: 'Me', mascot: null },
        score: me.score ?? 0,
        correct_answers: me.correct ?? 0,
        total_answer_time_ms: me.timeMs ?? 0,
        is_winner: me.won ?? false,
        left_at: null,
      },
      {
        player: { id: THEM, display_name: 'Them', mascot: null },
        score: 0,
        correct_answers: 0,
        total_answer_time_ms: 0,
        is_winner: them.won ?? false,
        left_at: null,
      },
    ],
  }
}

describe('resultFor', () => {
  it('reads a win, a loss and a draw off the same shape', () => {
    expect(resultFor(match({ me: { won: true } }), ME)).toBe('win')
    expect(resultFor(match({ me: {}, them: { won: true } }), ME)).toBe('loss')
    expect(resultFor(match({ me: {} }), ME)).toBe('draw')
  })

  it('is null for a match this player was not in', () => {
    expect(resultFor(match({ me: { won: true } }), 'stranger')).toBeNull()
  })
})

describe('currentStreak', () => {
  it('counts the newest run only', () => {
    expect(currentStreak(['win', 'win', 'loss', 'win'])).toEqual({ result: 'win', length: 2 })
  })

  it('is broken by a draw rather than extended by it', () => {
    expect(currentStreak(['draw', 'win', 'win'])).toEqual({ result: 'draw', length: 1 })
  })

  it('is null with nothing played', () => {
    expect(currentStreak([])).toBeNull()
  })
})

describe('summarisePlayerForm', () => {
  it('counts every finished match toward the record', () => {
    const form = summarisePlayerForm(
      [
        match({ me: { won: true } }),
        match({ me: {}, them: { won: true }, outcome: 'abandoned' }),
        match({ me: {} }),
      ],
      ME,
    )
    expect([form.wins, form.losses, form.draws]).toEqual([1, 1, 1])
    expect(form.played).toBe(3)
    expect(form.winRate).toBe(33)
  })

  it('measures accuracy and speed over played-out matches only', () => {
    const form = summarisePlayerForm(
      [
        match({ me: { correct: 4, score: 300, timeMs: 10_000 }, questions: 5 }),
        // Abandoned: three of its five questions were never asked, so counting
        // them would report the player who stayed as 0-for-3.
        match({ me: { correct: 1, score: 80, timeMs: 3_000 }, questions: 5, outcome: 'abandoned' }),
      ],
      ME,
    )
    expect(form.accuracy).toBe(80)
    expect(form.avgPoints).toBe(300)
    expect(form.avgAnswerMs).toBe(2_000)
  })

  it('caps accuracy when sudden death added questions past the agreed length', () => {
    const form = summarisePlayerForm([match({ me: { correct: 6 }, questions: 5 })], ME)
    expect(form.accuracy).toBe(100)
  })

  it('reports nothing rather than zeroes for a player who has not played', () => {
    const form = summarisePlayerForm([], ME)
    expect(form).toMatchObject({
      played: 0,
      winRate: null,
      accuracy: null,
      avgPoints: null,
      avgAnswerMs: null,
      bestScore: null,
      streak: null,
    })
  })

  it('keeps the best single-match score, including from an abandoned one', () => {
    const form = summarisePlayerForm(
      [match({ me: { score: 120 } }), match({ me: { score: 410 }, outcome: 'abandoned' })],
      ME,
    )
    expect(form.bestScore).toBe(410)
  })
})
