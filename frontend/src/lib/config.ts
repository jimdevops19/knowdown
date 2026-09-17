/*
 * Central runtime config, sourced from Vite env vars (`.env`, `VITE_`-prefixed
 * only — see `.env.example`). One file to override per deployment instead of
 * hunting for magic numbers and URLs across components.
 */

function positiveIntEnv(raw: string | undefined, fallback: number): number {
  const n = Number(raw)
  return raw !== undefined && Number.isFinite(n) && n > 0 ? n : fallback
}

/** Base origin the API client prepends before `/api/v1`. Empty in dev — the Vite proxy handles it. */
export const API_URL = import.meta.env.VITE_API_URL ?? ''

/** Google OAuth client id for the "Continue with Google" button. Unset hides it. */
export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined

/**
 * Base origin for the realtime WebSocket. Empty (the default) means "same
 * origin as the page", which is what both deployments actually are: the Vite
 * dev proxy and the production nginx each forward `/ws/` to the realtime
 * service. Set it only when the socket must cross an origin — a frontend served
 * from somewhere other than the thing proxying the API.
 *
 * The scheme is not configured here: it is derived from the page's own, so an
 * https page never opens an insecure socket by way of a stale env var.
 */
export const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) ?? ''

/**
 * The countdown's width when there is no question open — mirroring
 * `apps.matches.constants.FALLBACK_QUESTION_TIME_LIMIT_SECONDS`.
 *
 * **Not the limit any live question is drawn against.** Each `question.started`
 * carries the server's own `time_limit_ms` for that question (it varies by type
 * and by the question's authored override), and `useQuestionClock` draws that.
 * This number only gives the parked bar between questions a width.
 *
 * **This number is only ever used to draw a bar.** The server stamps the
 * question, the server closes it, and the server measures the response time it
 * scores; the client's clock is a picture of the server's decision, never an
 * input to it. That is the whole reason a mismatch here is cosmetic rather than
 * exploitable — a client that shortened it would only lie to its own player,
 * and one that lengthened it would show a bar still running on a question that
 * has already closed.
 *
 * It lives in config rather than as a constant so a deployment that retunes the
 * backend's fallback can retune the picture to match without a rebuild.
 */
export const QUESTION_TIME_LIMIT_MS = positiveIntEnv(
  import.meta.env.VITE_QUESTION_TIME_LIMIT_MS,
  10_000,
)

/**
 * How long a question sits on screen before its countdown starts ticking, in
 * milliseconds — mirroring `apps.matches.constants.QUESTION_READ_DELAY_SECONDS`.
 *
 * The board renders the moment `question.started` arrives; only the clock's
 * zero-point is pushed out by this much (`useMatchup`'s `seenAt`), so a
 * player gets a beat to read the question before the bar is doing anything.
 * Purely a picture of the server's own delay — same status as
 * `QUESTION_TIME_LIMIT_MS` above, and for the same reason: the server, not
 * this constant, is what actually holds a submission arriving during the
 * delay to be "answered instantly" rather than refused.
 */
export const QUESTION_READ_DELAY_MS = positiveIntEnv(
  import.meta.env.VITE_QUESTION_READ_DELAY_MS,
  3_000,
)

/**
 * How long the server gives a disconnected player to come back before their
 * opponent is awarded the win — `apps.matches.constants.RECONNECT_GRACE_SECONDS`.
 *
 * Same status as the number above: the client counts it down to explain what
 * the opponent-disconnected banner is waiting for, and the *ending* still
 * arrives as an ordinary `match.completed` from the server. The banner must
 * never conclude the match by itself when the count reaches zero, or a player
 * whose opponent reconnected on the last tick would be shown a win they did
 * not get.
 */
export const RECONNECT_GRACE_MS = positiveIntEnv(
  import.meta.env.VITE_RECONNECT_GRACE_MS,
  20_000,
)
