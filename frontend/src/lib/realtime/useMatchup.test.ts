import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PlayQuestion } from '../api/types'
import type { ServerMessage } from './messages'
import type { ConnectionState } from './socket'

/*
 * The match state machine, driven straight off the event stream.
 *
 * The socket is mocked down to a pair of callbacks, which is the whole point:
 * every rule under test — what a reconnect does to a submission, when the
 * running score stops being trustworthy, what `player.answered` may and may not
 * say — is a decision the reducer makes, and none of it should need a server, a
 * network or a timer to exercise. This mirrors the discipline the backend
 * follows in the other direction, where every rule of the game is a service
 * function a test can call with no socket in sight.
 */

let emit: (message: ServerMessage) => void
let setState: (state: ConnectionState, closeCode?: number) => void
const send = vi.fn(() => true)
const unsubscribe = vi.fn()

vi.mock('./socket', () => ({
  subscribe: (
    _path: string,
    _isHandshake: unknown,
    onMessage: (message: ServerMessage) => void,
    onState: (state: ConnectionState, closeCode?: number) => void,
  ) => {
    emit = onMessage
    setState = onState
    return { unsubscribe, send }
  },
}))

const { useMatchup } = await import('./useMatchup')
const { CLOSE_NOT_FOUND } = await import('./messages')

const ME = 'player-me'
const RIVAL = 'player-rival'

function question(id: string): PlayQuestion {
  return {
    id,
    type: 'single-answer',
    description: `Question ${id}`,
    level: 4,
    category: 'nba',
    image: null,
    pre_question_info: '',
    options: [
      { id: 1, text: 'A' },
      { id: 2, text: 'B' },
    ],
  }
}

function open(order: number, id = `q-${order}`, timeLimitMs = 10_000, startedAtMs = Date.now()) {
  act(() =>
    emit({
      type: 'question.started',
      order,
      question: question(id),
      time_limit_ms: timeLimitMs,
      started_at_ms: startedAtMs,
    }),
  )
}

function hint(order: number, index: number, text: string) {
  act(() => emit({ type: 'hint.revealed', order, index, text }))
}

function close(order: number, entries: { player_id: string; points: number }[]) {
  act(() =>
    emit({
      type: 'question.result',
      order,
      results: entries.map((entry) => ({
        ...entry,
        is_correct: entry.points > 0,
        score: entry.points > 0 ? 1 : 0,
        response_time_ms: 1200,
      })),
    }),
  )
}

beforeEach(() => {
  send.mockClear()
  unsubscribe.mockClear()
})

describe('useMatchup', () => {
  it('opens a question and accepts one answer', () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))

    open(1)
    expect(result.current.phase).toBe('question')
    expect(result.current.canAnswer).toBe(true)

    act(() => result.current.answer({ type: 'single-answer', option_id: 2 }))

    expect(send).toHaveBeenCalledWith({
      type: 'answer.submit',
      order: 1,
      // No `response_time_ms`: the server measures it against its own stamp and
      // rejects a payload carrying one as malformed. If this assertion ever
      // needs relaxing, something has gone badly wrong.
      payload: { type: 'single-answer', option_id: 2 },
    })
    expect(result.current.canAnswer).toBe(false)
  })

  it("carries the server's own time limit for each question", () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))

    // A matrix board is authored with far more clock than the default ten
    // seconds. Drawing the default over it would run the countdown to zero
    // while the server still held the question open, which reads to the player
    // as the match hanging on their opponent.
    open(1, 'q-1', 35_000)
    expect(result.current.current?.timeLimitMs).toBe(35_000)

    close(1, [{ player_id: ME, points: 10 }])
    open(2, 'q-2')
    expect(result.current.current?.timeLimitMs).toBe(10_000)
  })

  it('does not mark an answer as sent when the socket is down', () => {
    send.mockReturnValueOnce(false)
    const { result } = renderHook(() => useMatchup('m-1', ME))
    open(1)

    act(() => result.current.answer({ type: 'single-answer', option_id: 1 }))

    // Nothing is queued for the reconnect: it would arrive against a question
    // that has since closed and be refused, while the player — who watched
    // their tile light up — would believe they answered in time.
    expect(result.current.mySubmission).toBeNull()
    expect(result.current.canAnswer).toBe(true)
  })

  it('reports that the opponent answered, and never what they said', () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))
    open(1)

    act(() => emit({ type: 'player.answered', order: 1, player_id: RIVAL }))

    expect(result.current.opponentAnswered).toBe(true)
    // The message shape simply has nowhere to put a verdict, and the state
    // shape has nowhere to keep one. This asserts the second half.
    expect(result.current.results).toBeNull()
  })

  it('ignores my own answer notice as an opponent signal', () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))
    open(1)

    act(() => emit({ type: 'player.answered', order: 1, player_id: ME }))

    expect(result.current.opponentAnswered).toBe(false)
  })

  it('accumulates points across questions', () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))

    open(1)
    close(1, [
      { player_id: ME, points: 80 },
      { player_id: RIVAL, points: 0 },
    ])
    open(2)
    close(2, [
      { player_id: ME, points: 60 },
      { player_id: RIVAL, points: 90 },
    ])

    expect(result.current.scores).toEqual({ [ME]: 140, [RIVAL]: 90 })
    expect(result.current.scoresComplete).toBe(true)
  })

  it('keeps my submission when the same question is re-sent after a reconnect', () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))
    open(1, 'q-1')
    act(() => result.current.answer({ type: 'single-answer', option_id: 1 }))

    act(() => setState('connecting'))
    // The server re-sends the question in progress, same order, on reconnect.
    open(1, 'q-1')

    // Re-offering the board would let a player answer twice. The server refuses
    // the second, but the UI would have lied to them in between.
    expect(result.current.mySubmission).toEqual({ type: 'single-answer', option_id: 1 })
    expect(result.current.canAnswer).toBe(false)
  })

  it('stops trusting the running score when a question was missed', () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))

    open(1)
    close(1, [{ player_id: ME, points: 100 }])
    // Away for question 2; back in time for question 3. The results for 2 were
    // never delivered, so the total this client holds is quietly short.
    open(3)

    expect(result.current.scoresComplete).toBe(false)
  })

  it("restores the score from the server's own totals when the match ends", () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))

    open(1)
    close(1, [{ player_id: ME, points: 100 }])
    open(3) // a gap, as above

    act(() =>
      emit({
        type: 'match.completed',
        outcome: 'played',
        winner_player_id: RIVAL,
        scores: { [ME]: 100, [RIVAL]: 260 },
      }),
    )

    expect(result.current.phase).toBe('completed')
    // `match.completed` is authoritative even for a client that missed half the
    // match, so confidence comes back with it.
    expect(result.current.scores).toEqual({ [ME]: 100, [RIVAL]: 260 })
    expect(result.current.scoresComplete).toBe(true)
  })

  it('unlocks the board when the server refuses a submission', () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))
    open(1)
    act(() => result.current.answer({ type: 'single-answer', option_id: 1 }))

    act(() => emit({ type: 'error', code: 'validation_failed', message: 'Malformed answer.' }))

    expect(result.current.mySubmission).toBeNull()
    expect(result.current.canAnswer).toBe(true)
    expect(result.current.error?.message).toBe('Malformed answer.')
  })

  it('tracks the opponent leaving and coming back', () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))
    open(1)

    act(() => emit({ type: 'opponent.disconnected', player_id: RIVAL }))
    expect(result.current.opponentAway).toBe(true)

    act(() => emit({ type: 'opponent.reconnected', player_id: RIVAL }))
    expect(result.current.opponentAway).toBe(false)
  })

  it("draws the clock from the server's stamp, not from when this client saw the frame", () => {
    // A hard page refresh, not just a dropped socket: this `useMatchup`
    // instance has never seen the match before, so `state.current` starts
    // null and the "resuming" heuristic that used to gate the clock stamp
    // cannot fire. The question the server hands back may already be several
    // seconds into its time limit — `started_at_ms` says so — and the client
    // must draw the countdown from that real zero-point rather than minting
    // a fresh one from `Date.now()`, which would hand the player a reset
    // timer for a question the server is about to close.
    const { result } = renderHook(() => useMatchup('m-1', ME))
    const startedAtMs = Date.now() - 7_000 // already 7s into a 10s question
    open(1, 'q-1', 10_000, startedAtMs)

    expect(result.current.current?.seenAt).toBe(startedAtMs)
  })

  it('holds the board on screen through a reconnect rather than blanking it', () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))
    open(1)

    act(() => setState('connecting'))

    // A reconnect that completes in 300ms must not flash an empty board at
    // somebody with six seconds left.
    expect(result.current.current?.order).toBe(1)
  })

  it('goes unavailable on a permanent close, carrying the code', () => {
    const { result } = renderHook(() => useMatchup('m-1', ME))

    act(() => setState('closed', CLOSE_NOT_FOUND))

    expect(result.current.phase).toBe('unavailable')
    expect(result.current.closeCode).toBe(CLOSE_NOT_FOUND)
  })

  it('subscribes to nothing without a matchup id', () => {
    renderHook(() => useMatchup(null, ME))
    expect(send).not.toHaveBeenCalled()
  })

  describe('gradual hints', () => {
    /*
     * The clues are the only part of a question that arrives after the board,
     * which makes them the only part with a lifecycle worth testing: they have
     * to attach to the right question, survive a reconnect without doubling,
     * and stop when the question does.
     */

    it('accumulates the clues of the open question in reveal order', () => {
      const { result } = renderHook(() => useMatchup('m-1', ME))
      open(1)
      hint(1, 1, 'The final score was 93-89')
      hint(1, 2, 'It went seven games')

      expect(result.current.hints).toEqual([
        'The final score was 93-89',
        'It went seven games',
      ])
    })

    it('drops a clue that is not for the question on screen', () => {
      // The reveal of a question the pair answered early keeps running
      // server-side; a clue landing under the next question's text would be a
      // hint to the wrong question.
      const { result } = renderHook(() => useMatchup('m-1', ME))
      open(1)
      hint(1, 1, 'For question one')
      close(1, [{ player_id: ME, points: 80 }])
      open(2)
      hint(1, 2, 'Still for question one')

      expect(result.current.hints).toEqual([])
    })

    it('drops a clue that arrives after the question closed', () => {
      const { result } = renderHook(() => useMatchup('m-1', ME))
      open(1)
      hint(1, 1, 'Before the verdict')
      close(1, [{ player_id: ME, points: 80 }])
      hint(1, 2, 'After the verdict')

      expect(result.current.hints).toEqual(['Before the verdict'])
    })

    it('does not double a clue replayed by a reconnect', () => {
      // A socket that comes back mid-question is re-sent the board *and* every
      // clue already due — the catch-up and the live reveal are the same code
      // path on the server, so the client is what has to be idempotent.
      const { result } = renderHook(() => useMatchup('m-1', ME))
      const startedAt = Date.now()
      open(1, 'q-1', 40_000, startedAt)
      hint(1, 1, 'First clue')
      hint(1, 2, 'Second clue')

      open(1, 'q-1', 40_000, startedAt) // the reconnect's re-sent board
      hint(1, 1, 'First clue')
      hint(1, 2, 'Second clue')

      expect(result.current.hints).toEqual(['First clue', 'Second clue'])
    })

    it('starts a new question with no clues', () => {
      const { result } = renderHook(() => useMatchup('m-1', ME))
      open(1)
      hint(1, 1, 'For question one')
      close(1, [{ player_id: ME, points: 80 }])
      open(2)

      expect(result.current.hints).toEqual([])
    })
  })
})
