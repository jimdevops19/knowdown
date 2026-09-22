/*
 * What a player's own match history *says* about them, computed on the client.
 *
 * Every number here is derived from rows the API already sends — `GET
 * /matches/` carries both sides' score, correct answers and total answer time
 * per finished match — rather than from a stats endpoint, because there isn't
 * one and this is the wrong reason to add one: these are summaries of a page of
 * history, not facts the server is the authority on. A rating is the opposite
 * (the server owns it, `apps.rankings`) and is read from the profile.
 *
 * Pure functions, no React, so the arithmetic that decides "4 wins in a row" is
 * testable without rendering a page.
 */

import type { MatchupSummary } from '../../lib/api/types'

export type MatchResult = 'win' | 'loss' | 'draw'

/** How one match ended *for this player*, or null if they weren't in it. */
export function resultFor(match: MatchupSummary, playerId: string | null): MatchResult | null {
  const me = match.players.find((side) => side.player.id === playerId)
  if (!me) return null
  if (me.is_winner) return 'win'
  // A match nobody won is a draw; anything else with a winner in it is a loss.
  return match.players.some((side) => side.is_winner) ? 'loss' : 'draw'
}

/** The current run: 3 wins, 2 losses, whatever the newest matches agree on.
 *  Null for a player with no finished matches. Drawn matches break a streak
 *  rather than extending it — a draw is not a win and not a loss. */
export function currentStreak(
  results: MatchResult[],
): { result: MatchResult; length: number } | null {
  const [first] = results
  if (!first) return null
  let length = 1
  while (length < results.length && results[length] === first) length += 1
  return { result: first, length }
}

export interface PlayerForm {
  /** Newest first, exactly as the history arrives. */
  results: MatchResult[]
  wins: number
  losses: number
  draws: number
  streak: { result: MatchResult; length: number } | null
  /** Matches played, by this window. */
  played: number
  /** Wins as a whole percent, or null for a player who hasn't played. */
  winRate: number | null
  /** Correct answers over questions asked, as a whole percent. Null until at
   *  least one match was *played out* — an abandoned match's unasked questions
   *  would otherwise count against the player who stayed. */
  accuracy: number | null
  /** Mean points per match, over played-out matches. */
  avgPoints: number | null
  /** Mean time to answer one question, in ms, over played-out matches. */
  avgAnswerMs: number | null
  /** The best single-match score in this window. Null with nothing played. */
  bestScore: number | null
}

/**
 * Summarise a page of finished matches for one player.
 *
 * Two windows on purpose: results, streak and win rate count **every** finished
 * match, because an abandoned match still moved the ladder and still counts as
 * a win or a loss (`apps.matches.services.abandon_matchup`). Accuracy, points
 * and answer speed count only matches with `outcome: "played"` — a match
 * somebody walked out of has questions nobody was asked, and dividing by them
 * would report a player as less accurate for their opponent leaving.
 */
export function summarisePlayerForm(
  matches: MatchupSummary[],
  playerId: string | null,
): PlayerForm {
  const results: MatchResult[] = []
  let wins = 0
  let losses = 0
  let draws = 0

  let correct = 0
  let asked = 0
  let points = 0
  let answerMs = 0
  let playedOut = 0
  let bestScore: number | null = null

  for (const match of matches) {
    const result = resultFor(match, playerId)
    if (!result) continue
    results.push(result)
    if (result === 'win') wins += 1
    else if (result === 'loss') losses += 1
    else draws += 1

    const me = match.players.find((side) => side.player.id === playerId)
    if (!me) continue
    if (bestScore === null || me.score > bestScore) bestScore = me.score
    if (match.outcome !== 'played') continue
    playedOut += 1
    correct += me.correct_answers
    asked += match.question_count
    points += me.score
    answerMs += me.total_answer_time_ms
  }

  const played = results.length
  return {
    results,
    wins,
    losses,
    draws,
    streak: currentStreak(results),
    played,
    winRate: played > 0 ? Math.round((wins / played) * 100) : null,
    // Capped: sudden death appends questions past `question_count`, so a match
    // decided in overtime can have more correct answers than it agreed to ask.
    accuracy: asked > 0 ? Math.min(100, Math.round((correct / asked) * 100)) : null,
    avgPoints: playedOut > 0 ? Math.round(points / playedOut) : null,
    avgAnswerMs: asked > 0 ? Math.round(answerMs / asked) : null,
    bestScore,
  }
}
