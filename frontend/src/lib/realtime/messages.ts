import type { PlayQuestion, AnswerSubmission } from '../api/types'

/*
 * The message contract, mirroring `backend/apps/matches/events.py`. Both halves
 * are small enough to read side by side, and they have to be changed together —
 * a rename on one side is a socket that goes quiet rather than an error
 * anywhere.
 *
 * ── How this differs from a "thin event" socket, and why ────────────────────
 * A realtime layer that only ever says "match {id} changed, go refetch" is the
 * right design when the REST endpoint is the source of truth and the socket
 * only decides *when* to ask. It is the wrong design here, and the reason is
 * the clock: a question is open for ten seconds, the server stamped it, and the
 * response time it scores is measured against that stamp. There is nothing to
 * refetch mid-question — a round trip to ask "what is the question?" would be
 * the exact latency the game is measuring.
 *
 * So these payloads are **fat**: `question.started` carries the whole board.
 * The rule that replaces "keep messages thin" is the one this file exists to
 * enforce, and it is the same rule the play-time serializers enforce on the
 * other side:
 *
 *   **Nothing that crosses this socket while a clock is running may identify a
 *   correct answer.**
 *
 * `question.started` carries a board with no answer in it (the backend refuses
 * to boot if a serializer declares one). `player.answered` says *who* answered,
 * never *what they said or whether they were right* — the opponent's clock is
 * still going, and "your rival locked in" is a fact; "your rival locked in and
 * was right" would be the answer. Only `question.result`, sent once both sides
 * are done or the clock has expired, carries a verdict.
 *
 * The one write a client may make is `answer.submit`. Everything else — who the
 * players are, which question is open, whether an answer is correct, how long
 * it took — is decided from server state and never trusted off the wire.
 */

/* --- Matchmaking socket: /ws/v1/matchmaking/{category}/ -------------------- */

/** Sent once, right after connect, before a pairing is even possible: the cue
 *  to stop showing a spinner the client drew itself and start trusting the
 *  server's. Its arrival is also what proves the subscription is live. */
export const SEARCHING = 'searching'

/** A pairing happened. Carries the matchup id and nothing about either player —
 *  the client switches to the matchup socket to learn anything else. */
export const MATCH_FOUND = 'match.found'

/** Client → server: give up the search. The only write this socket takes
 *  besides connecting. */
export const SEARCH_CANCEL = 'search.cancel'

/* --- Matchup socket: /ws/v1/matches/{matchup_id}/ -------------------------- */

/** One question opened. `T0` is the server's, not a promise the client makes
 *  itself. Carries the play-time board — never a field naming an answer. */
export const QUESTION_STARTED = 'question.started'

/** One player answered. Who, not what. */
export const PLAYER_ANSWERED = 'player.answered'

/** The question closed — everyone answered, or the clock ran out. The one
 *  message allowed to carry a verdict. */
export const QUESTION_RESULT = 'question.result'

/** The matchup reached COMPLETED. Carries the final score line and the winner
 *  (or null, on the score-and-time double tie the server leaves unbroken). */
export const MATCH_COMPLETED = 'match.completed'

/** The opponent's socket dropped. **Informational only** — it starts no clock
 *  the client may act on. The server ends the matchup after its own grace
 *  period, and that ending arrives as an ordinary `match.completed`. */
export const OPPONENT_DISCONNECTED = 'opponent.disconnected'

/** The opponent came back before the grace period ran out. */
export const OPPONENT_RECONNECTED = 'opponent.reconnected'

/** Client → server: an answer to the question currently open. */
export const ANSWER_SUBMIT = 'answer.submit'

/* --- Both sockets ---------------------------------------------------------- */

/** A submission the server refused — malformed, or aimed at a question that is
 *  already closed. Carries the same `code`/`message` shape as a REST 4xx, so
 *  one error model serves both transports (see `lib/api/errors.ts`). */
export const ERROR = 'error'

/** Client → server and back, to hold an idle socket open through a proxy. */
export const PING = 'ping'
export const PONG = 'pong'

/* --- Server → client payloads ---------------------------------------------- */

export interface SearchingMessage {
  type: typeof SEARCHING
}

export interface MatchFoundMessage {
  type: typeof MATCH_FOUND
  matchup_id: string
}

export interface QuestionStartedMessage {
  type: typeof QUESTION_STARTED
  /** 1-based position in the match. Also the handle an answer is submitted
   *  against, so a late answer to question 2 cannot be applied to question 3. */
  order: number
  question: PlayQuestion
}

export interface PlayerAnsweredMessage {
  type: typeof PLAYER_ANSWERED
  order: number
  player_id: string
}

/** One player's verdict on one question. `score` is credit (0.0–1.0) and
 *  `points` is what that credit was worth once speed was applied — they are two
 *  numbers because a matrix can be partly right. */
export interface QuestionResultEntry {
  player_id: string
  is_correct: boolean
  score: number
  points: number
  response_time_ms: number
}

/** Note what a result does *not* contain: the correct answer. The server tells
 *  each player whether they were right, and does not publish the key — a
 *  question can come up again in a later match. */
export interface QuestionResultMessage {
  type: typeof QUESTION_RESULT
  order: number
  /** One entry per player who answered. A player who ran out of time has no
   *  entry at all, which is how "didn't answer" is told from "answered wrong". */
  results: QuestionResultEntry[]
}

export interface MatchCompletedMessage {
  type: typeof MATCH_COMPLETED
  /** `played` or `abandoned`. Both move the ladder the same way. */
  outcome: 'played' | 'abandoned'
  /** Null on the double tie the server leaves unbroken. */
  winner_player_id: string | null
  /** Final points, by player id. */
  scores: Record<string, number>
}

export interface OpponentPresenceMessage {
  type: typeof OPPONENT_DISCONNECTED | typeof OPPONENT_RECONNECTED
  player_id: string
}

export interface ErrorMessage {
  type: typeof ERROR
  code: string
  message: string
}

export interface PongMessage {
  type: typeof PONG
}

export type ServerMessage =
  | SearchingMessage
  | MatchFoundMessage
  | QuestionStartedMessage
  | PlayerAnsweredMessage
  | QuestionResultMessage
  | MatchCompletedMessage
  | OpponentPresenceMessage
  | ErrorMessage
  | PongMessage

/* --- Client → server payloads ---------------------------------------------- */

export interface AnswerSubmitMessage {
  type: typeof ANSWER_SUBMIT
  order: number
  payload: AnswerSubmission
}

/* --- Close codes ------------------------------------------------------------
 * The 4000–4999 range is reserved for the application, which is how a client
 * tells a permanent close (stop retrying) from a transport failure (back off
 * and try again). */

/** Not signed in, or the token expired while connecting. Permanent. */
export const CLOSE_UNAUTHENTICATED = 4401

/** The subject does not exist — or exists and is not yours. **The server
 *  deliberately does not tell the two apart**, so a stranger cannot probe which
 *  matchup ids are real. Permanent either way. */
export const CLOSE_NOT_FOUND = 4404

/** The matchmaking socket's one job is done: a pairing happened and the client
 *  should now open the matchup socket. A *normal* close, not a failure — it
 *  arrives immediately after `match.found`. */
export const CLOSE_MATCHED = 4200

/** The matchmaking pool was too busy to take the join. Transient — the standard
 *  "try again later" code, so backing off and retrying is the right response. */
export const CLOSE_POOL_BUSY = 1013

/**
 * Too many sockets, or too many joins, for this account —
 * `apps.matches.abuse`, mirroring HTTP 429 into the application range.
 *
 * Permanent *here*, which is the counter-intuitive part: the connection is
 * refused precisely because this client has been connecting too much, so the
 * one thing a reconnect loop must not do is reconnect. Backing off would still
 * be reconnecting, just politely. The player retries by hand, or closes the
 * other tab that is holding the sockets.
 */
export const CLOSE_RATE_LIMITED = 4429

/** Close codes that mean "do not reconnect". A `CLOSE_MATCHED` belongs here for
 *  a different reason than the others: not that reconnecting would fail, but
 *  that it would put the player back in the queue for a match they have already
 *  been given. */
export const PERMANENT_CLOSE_CODES: readonly number[] = [
  CLOSE_UNAUTHENTICATED,
  CLOSE_NOT_FOUND,
  CLOSE_MATCHED,
  CLOSE_RATE_LIMITED,
]
