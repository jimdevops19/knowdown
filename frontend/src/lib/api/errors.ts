import { AxiosError } from 'axios'

/*
 * Every backend failure is normalized to a single envelope
 * (`apps.core_common.exceptions`):
 *   { error: { code, message, details?, request_id? } }
 * This module turns any failure — that envelope, a raw HTTP error, or a network
 * drop — into one typed `ApiError` the whole app can reason about.
 *
 * The same shape arrives over the socket, too: `events.ERROR` carries a
 * `code`/`message` pair deliberately identical to a REST 4xx, so one error
 * model serves both transports (see `lib/realtime/messages.ts`).
 */

export type ApiErrorCode =
  | 'validation_failed'
  | 'not_found'
  | 'permission_denied'
  | 'conflict'
  | 'matchup_in_progress'
  | 'domain_error'
  | 'authentication_failed'
  | 'rate_limited'
  | 'network_error'
  | 'unknown'

/** Default human copy per code; a server-provided message wins over these. */
const CODE_MESSAGES: Record<ApiErrorCode, string> = {
  validation_failed: 'Please check the highlighted fields.',
  not_found: "We couldn't find what you were looking for.",
  permission_denied: "You don't have access to do that.",
  conflict: 'That conflicts with what has already happened.',
  // `GET /matches/{id}/` refuses until the match is over — a box score of a
  // game still being played would carry the questions nobody has been asked
  // yet and the opponent's answer to the one that is open. Reaching this in
  // the UI means something navigated to a summary too early, so the copy
  // points at the game rather than reading as a failure.
  matchup_in_progress: 'That match is still being played.',
  domain_error: 'That isn’t allowed right now.',
  authentication_failed: 'Please sign in and try again.',
  // Sent over the socket mid-match (`apps.matches.abuse`) rather than closing
  // it — a burst of taps is not a reason to end somebody's game. So the copy is
  // written to be read *during* a question, not as a page-level failure.
  rate_limited: 'Slow down a moment — that was a lot of taps.',
  network_error: "Can't reach the server. Check your connection.",
  unknown: 'Something went wrong. Please try again.',
}

export class ApiError extends Error {
  readonly code: ApiErrorCode
  /** Structured, possibly per-field details (e.g. { email: ["..."] }). */
  readonly details?: Record<string, unknown>
  /** Correlation id (also on the X-Request-ID header) — surface it in dev. */
  readonly requestId?: string
  /** HTTP status, when there was a response. Absent for a socket error. */
  readonly status?: number

  constructor(args: {
    code: ApiErrorCode
    message: string
    details?: Record<string, unknown>
    requestId?: string
    status?: number
  }) {
    super(args.message)
    this.name = 'ApiError'
    this.code = args.code
    this.details = args.details
    this.requestId = args.requestId
    this.status = args.status
  }
}

/** Shape of the backend's error envelope body. */
interface ErrorEnvelope {
  error?: {
    code?: string
    message?: string
    details?: Record<string, unknown>
    request_id?: string
  }
}

function isKnownCode(code: string | undefined): code is ApiErrorCode {
  return !!code && code in CODE_MESSAGES
}

/** Convert anything thrown by axios into an ApiError. */
export function normalizeApiError(error: unknown): ApiError {
  // Idempotent: the axios error interceptor already normalizes failures to an
  // ApiError, so callers (mutation.error, a rethrow) hand us one that is done.
  // Re-running the AxiosError path on it would fall through to the generic
  // `unknown` message and discard the real one. Return it untouched instead.
  if (error instanceof ApiError) return error

  if (error instanceof AxiosError) {
    const status = error.response?.status
    const body = error.response?.data as ErrorEnvelope | undefined
    const envelope = body?.error

    // No response at all → the request never completed (network/timeout/CORS).
    if (!error.response) {
      return new ApiError({ code: 'network_error', message: CODE_MESSAGES.network_error })
    }

    const code: ApiErrorCode = isKnownCode(envelope?.code) ? envelope.code : 'unknown'
    return new ApiError({
      code,
      message: envelope?.message || CODE_MESSAGES[code],
      details: envelope?.details,
      requestId: envelope?.request_id,
      status,
    })
  }

  // Not an axios error — shouldn't normally happen past the interceptor.
  return new ApiError({ code: 'unknown', message: CODE_MESSAGES.unknown })
}

/**
 * The socket's counterpart. `events.ERROR` carries the same `code`/`message`
 * pair a REST 4xx does (see `apps/matches/events.py`), so a refusal that
 * arrives over the socket can be shown by the same components — with no HTTP
 * status, because there was no response to carry one.
 */
export function apiErrorFromSocket(code: string | undefined, message: string | undefined): ApiError {
  const known: ApiErrorCode = isKnownCode(code) ? code : 'domain_error'
  return new ApiError({ code: known, message: message || CODE_MESSAGES[known] })
}

/** Per-field messages out of `details`, flattened for a form to display. */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !error.details) return {}
  const out: Record<string, string> = {}
  for (const [field, value] of Object.entries(error.details)) {
    if (Array.isArray(value)) out[field] = String(value[0])
    else if (typeof value === 'string') out[field] = value
  }
  return out
}
