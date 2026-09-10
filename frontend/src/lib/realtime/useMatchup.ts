import { useCallback, useEffect, useReducer, useRef } from 'react'
import type { AnswerSubmission, PlayQuestion } from '../api/types'
import { ApiError, apiErrorFromSocket } from '../api/errors'
import {
  ANSWER_SUBMIT,
  CLOSE_NOT_FOUND,
  CLOSE_RATE_LIMITED,
  CLOSE_UNAUTHENTICATED,
  ERROR,
  MATCH_COMPLETED,
  OPPONENT_DISCONNECTED,
  OPPONENT_RECONNECTED,
  PLAYER_ANSWERED,
  QUESTION_RESULT,
  QUESTION_STARTED,
  type MatchCompletedMessage,
  type QuestionResultEntry,
  type ServerMessage,
} from './messages'
import { subscribe, type ConnectionState, type Subscription } from './socket'

/*
 * A live matchup, as a state machine over the socket's event stream.
 *
 * This is the one place in the app that holds game state, and it holds it in a
 * reducer rather than in a handful of `useState`s on purpose: the events arrive
 * in bursts — a result, the next question and sometimes the final summary land
 * in the same tick — and every one of those transitions has to be applied in
 * order, from the previous state, without a stale closure in between. A
 * reducer makes "what does a `question.result` do to the board" a pure function
 * that can be read (and tested) on its own.
 *
 * **The client is never the referee.** It does not decide whether an answer was
 * right, when a question closes, or who won; it renders what the server said.
 * The clock it draws is a picture of the server's stamp (see `QUESTION_TIME_
 * LIMIT_MS`), not a timer whose expiry means anything — when it reaches zero
 * the board simply stops accepting taps, and the *actual* close arrives as a
 * `question.result` a moment later. A client whose clock ran fast would only
 * disadvantage its own player; one whose clock ran slow would let them tap a
 * tile the server then refuses, which is why an in-flight submission is shown
 * as pending rather than as answered.
 */

/** Which screen the match is on. */
export type MatchPhase =
  /** Opening the socket, or reconnecting. Nothing is on the board yet. */
  | 'connecting'
  /** A question is open and the clock is running. */
  | 'question'
  /** The question closed; the verdicts are up, and the next one is coming. */
  | 'result'
  /** The match is over. `completed` holds the final word. */
  | 'completed'
  /** Permanently unreachable — not signed in, or not your match. */
  | 'unavailable'

/** The question on the board, plus when *this client* saw it open. */
export interface LiveQuestion {
  order: number
  question: PlayQuestion
  /** `Date.now()` when the `question.started` frame arrived. Used only to draw
   *  the countdown, and deliberately not to compute a response time: the
   *  server measures that against its own stamp, and it is the only figure
   *  that is scored. The two differ by the trip time, which is precisely the
   *  latency the client must not be able to talk its way out of. */
  seenAt: number
}

export interface MatchupState {
  phase: MatchPhase
  /** The open question, or the one whose result is being shown. */
  current: LiveQuestion | null
  /** What this player submitted for `current.order`, if anything yet. Set the
   *  moment it goes out, so a tile can show as taken while the server thinks. */
  mySubmission: AnswerSubmission | null
  /** True once the opponent has locked in for `current.order`. Says nothing
   *  about *what* they said or whether it was right — that would be the answer,
   *  and this player's clock is still running. */
  opponentAnswered: boolean
  /** The verdicts for the question just closed. A player who ran out of time
   *  has no entry at all, which is how "didn't answer" is told from "wrong". */
  results: QuestionResultEntry[] | null
  /** Running points per player id, accumulated from every result seen. */
  scores: Record<string, number>
  /**
   * Whether `scores` is the whole story. A reconnect mid-match resumes at the
   * question in progress — the server re-sends *that* board and nothing about
   * the questions already played — so a client that came back cannot know the
   * score so far. It shows a dash rather than a number it made up; the real
   * total arrives with `match.completed`, which is authoritative.
   */
  scoresComplete: boolean
  /** True while the opponent's socket is away. Informational only: it starts no
   *  clock this client may act on. The server ends the match after its own
   *  grace period, and that ending arrives as an ordinary `match.completed`. */
  opponentAway: boolean
  /** The final word, once there is one. */
  completed: MatchCompletedMessage | null
  /** The last refusal from the server (a malformed answer, a closed question). */
  error: ApiError | null
  /** The code the socket was permanently closed with, when `phase` is
   *  `unavailable` — see {@link UNAVAILABLE_REASONS}. */
  closeCode: number | null
}

const INITIAL: MatchupState = {
  phase: 'connecting',
  current: null,
  mySubmission: null,
  opponentAnswered: false,
  results: null,
  scores: {},
  scoresComplete: true,
  opponentAway: false,
  completed: null,
  error: null,
  closeCode: null,
}

type Action =
  | { kind: 'message'; message: ServerMessage; myPlayerId: string | null }
  | { kind: 'state'; state: ConnectionState; closeCode?: number }
  | { kind: 'submitted'; submission: AnswerSubmission }

function reduce(state: MatchupState, action: Action): MatchupState {
  switch (action.kind) {
    case 'submitted':
      // Optimistic only in the narrow sense of "this tile is now taken". It
      // claims nothing about correctness, and the server may still refuse it —
      // in which case an `error` arrives and the board unlocks again.
      return { ...state, mySubmission: action.submission, error: null }

    case 'state': {
      if (action.state === 'closed') {
        return { ...state, phase: 'unavailable', closeCode: action.closeCode ?? null }
      }
      // A drop, or the first connect. The board is stale until the server
      // re-sends the question in progress, so hold the previous one on screen
      // rather than blanking it: a reconnect that completes in 300ms should not
      // flash an empty board at somebody with six seconds left.
      if (action.state === 'connecting' && state.phase !== 'completed') {
        return { ...state, phase: state.current ? state.phase : 'connecting' }
      }
      return state
    }

    case 'message': {
      const { message, myPlayerId } = action
      switch (message.type) {
        case QUESTION_STARTED: {
          // The first frame after a reconnect is this one, re-sent for the
          // question already in progress. Two consequences:
          //
          //  1. Re-receiving the *same* order must not reset the submission —
          //     a player who already answered and then blinked offline would
          //     otherwise be handed their board back and allowed to answer
          //     twice (the server refuses the second, but the UI would have
          //     lied to them in between).
          //  2. Skipping an order means results were missed while away, so the
          //     running score can no longer be trusted. Say so rather than
          //     showing a total that is quietly short.
          const resuming = state.current?.order === message.order
          const expected = (state.current?.order ?? 0) + 1
          return {
            ...state,
            phase: 'question',
            current: {
              order: message.order,
              question: message.question,
              // Keep the original stamp when resuming: the clock has been
              // running the whole time, and restarting it here would hand a
              // reconnecting player a fresh ten seconds on screen while the
              // server closes the question underneath them.
              seenAt: resuming && state.current ? state.current.seenAt : Date.now(),
            },
            mySubmission: resuming ? state.mySubmission : null,
            opponentAnswered: resuming ? state.opponentAnswered : false,
            results: resuming ? state.results : null,
            scoresComplete: state.scoresComplete && (resuming || message.order === expected),
            error: null,
          }
        }

        case PLAYER_ANSWERED: {
          if (message.order !== state.current?.order) return state
          if (myPlayerId && message.player_id === myPlayerId) return state
          return { ...state, opponentAnswered: true }
        }

        case QUESTION_RESULT: {
          if (message.order !== state.current?.order) return state
          const scores = { ...state.scores }
          for (const entry of message.results) {
            scores[entry.player_id] = (scores[entry.player_id] ?? 0) + entry.points
          }
          return { ...state, phase: 'result', results: message.results, scores }
        }

        case MATCH_COMPLETED:
          // The server's own totals replace whatever was accumulated, and
          // restore confidence in them: this is the authoritative score line
          // even for a client that missed half the match to a bad tunnel.
          return {
            ...state,
            phase: 'completed',
            completed: message,
            scores: message.scores,
            scoresComplete: true,
            opponentAway: false,
          }

        case OPPONENT_DISCONNECTED:
          return { ...state, opponentAway: true }

        case OPPONENT_RECONNECTED:
          return { ...state, opponentAway: false }

        case ERROR:
          // The refusal frees the board again — whatever this player thought
          // they submitted did not land, and they may still have time to try.
          return {
            ...state,
            mySubmission: null,
            error: apiErrorFromSocket(message.code, message.message),
          }

        default:
          return state
      }
    }
  }
}

export interface Matchup extends MatchupState {
  /** Submit an answer to the question currently open.
   *
   *  Refused locally when there is no open question, when this player has
   *  already answered it, or when the socket is not up — three cases the server
   *  would refuse anyway, caught here so the UI can stay honest about it rather
   *  than showing a tile as taken and un-taking it a round trip later. */
  answer: (submission: AnswerSubmission) => void
  /** Whether this player may still act on the current question. */
  canAnswer: boolean
}

/**
 * Watch and play one matchup.
 *
 * @param matchupId  the matchup to join, or null while the caller is still
 *                   resolving one (which subscribes to nothing).
 * @param myPlayerId this player's id, so `player.answered` and the score line
 *                   can be told apart from the opponent's. Null before the
 *                   session has hydrated; the hook degrades to treating every
 *                   answer notice as the opponent's, which is wrong only in the
 *                   window before /auth/me/ answers.
 */
export function useMatchup(matchupId: string | null, myPlayerId: string | null): Matchup {
  const [state, dispatch] = useReducer(reduce, INITIAL)
  const subscriptionRef = useRef<Subscription | null>(null)
  // Read through a ref so the effect below doesn't tear the socket down and
  // rebuild it the moment the session hydrates and `myPlayerId` changes.
  const playerIdRef = useRef(myPlayerId)
  playerIdRef.current = myPlayerId

  useEffect(() => {
    if (!matchupId) return

    // A matchup socket's handshake is its first `question.started`: the server
    // sends the question in progress as soon as it has joined the group. There
    // is no bare "connected" frame to key on, which is exactly as it should be
    // — being subscribed and having a board are the same event here.
    const isHandshake = (message: ServerMessage) => message.type === QUESTION_STARTED

    const subscription = subscribe(
      `/ws/v1/matches/${matchupId}/`,
      isHandshake,
      (message) => dispatch({ kind: 'message', message, myPlayerId: playerIdRef.current }),
      (connectionState, closeCode) => {
        dispatch({ kind: 'state', state: connectionState, closeCode })
      },
    )
    subscriptionRef.current = subscription

    return () => {
      subscriptionRef.current = null
      subscription.unsubscribe()
    }
  }, [matchupId])

  const canAnswer =
    state.phase === 'question' && state.current !== null && state.mySubmission === null

  const answer = useCallback(
    (submission: AnswerSubmission) => {
      const order = state.current?.order
      if (order === undefined || state.mySubmission !== null || state.phase !== 'question') return
      const sent = subscriptionRef.current?.send({ type: ANSWER_SUBMIT, order, payload: submission })
      // A send that never left is not an answer. Nothing is queued for the
      // reconnect: it would arrive against a question that has since closed and
      // be refused, while the player — who watched their tile light up — would
      // believe they answered in time.
      if (sent) dispatch({ kind: 'submitted', submission })
    },
    [state.current?.order, state.mySubmission, state.phase],
  )

  return { ...state, answer, canAnswer }
}

/** The close codes this hook turns into `phase: 'unavailable'`, and what each
 *  one means to a player. Exported so the screen can say something specific
 *  rather than "unavailable". */
export const UNAVAILABLE_REASONS: Record<number, string> = {
  [CLOSE_UNAUTHENTICATED]: 'Sign in to rejoin this match.',
  // The server answers "no such matchup" and "not your matchup" identically, on
  // purpose — otherwise a stranger could probe which matchup ids are real. So
  // this copy has to cover both without guessing which one happened.
  [CLOSE_NOT_FOUND]: "This match isn't yours, or no longer exists.",
  // Worth its own line rather than the generic fallback: unlike the two above,
  // this one clears on its own, so the copy should say to come back rather than
  // read as "this match is gone".
  [CLOSE_RATE_LIMITED]: 'Too many connections open for this account. Close your other tabs and rejoin.',
}
