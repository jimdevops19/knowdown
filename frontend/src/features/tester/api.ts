import { apiClient } from '../../lib/api/client'
import type {
  AnswerKey,
  AnswerSubmission,
  TesterConfig,
  TesterQuestionCard,
  TesterRehearsal,
  TesterVerdict,
} from '../../lib/api/types'
import type { Page } from '../../lib/api/endpoints'

/*
 * The tester's REST surface.
 *
 * In its own feature folder rather than in `lib/api/endpoints.ts`, for the
 * reason that file gives about auth: these belong to one feature, and this one
 * more than most — the endpoints exist on a tier only when the backend mounted
 * them, so putting them in the app's shared endpoint list would suggest they
 * are part of the API every build talks to. They are not. Every call here can
 * legitimately 404, and `useTesterAccess` is what reads that as "no".
 *
 * Note what is *not* here: anything resembling a match. A rehearsal opens no
 * socket, joins no pool and writes no row — it is three ordinary requests, and
 * the reason the real game is not built this way (a REST round trip is not a
 * clock, see `endpoints.ts`) does not apply when nobody is racing.
 */

/** `GET /tester/config/` 🔒 staff — the filter vocabulary, and the probe.
 *
 *  404 means the tier did not mount the tester; 403 means this account is not
 *  staff. The caller treats both the same way — no tester — and neither is an
 *  error worth showing anybody. */
export async function getTesterConfig(): Promise<TesterConfig> {
  const res = await apiClient.get<TesterConfig>('/tester/config/')
  return res.data
}

export interface TesterQuestionFilters {
  search?: string
  category?: string
  type?: string
  level_min?: number
  level_max?: number
  /** Defaults to true on the backend. Sent explicitly anyway so a change of
   *  default there cannot silently change what this page shows. */
  include_inactive?: boolean
  page?: number
  page_size?: number
}

/** `GET /tester/questions/` 🔒 staff — the catalog, across all eight tables. */
export async function listTesterQuestions(
  filters: TesterQuestionFilters = {},
): Promise<Page<TesterQuestionCard>> {
  const res = await apiClient.get<TesterQuestionCard[]>('/tester/questions/', {
    // Empty strings are dropped rather than sent: `?search=` would be a filter
    // that matches everything, which is the same as no filter and a different
    // cache key — so a cleared search box would refetch the same rows under a
    // new key every time it was cleared.
    params: Object.fromEntries(
      Object.entries(filters).filter(([, value]) => value !== undefined && value !== ''),
    ),
  })
  return { results: res.data, pagination: res.meta?.pagination }
}

/** `GET /tester/questions/{type}/{id}/` 🔒 staff — one question, staged.
 *
 *  `seed` decides the board order. Omitted, the backend uses a constant, so a
 *  reload does not reshuffle the options under someone mid-read; pass a fresh
 *  one to deal again. */
export async function getTesterRehearsal(
  questionType: string,
  questionId: string,
  seed?: string,
): Promise<TesterRehearsal> {
  const res = await apiClient.get<TesterRehearsal>(
    `/tester/questions/${questionType}/${questionId}/`,
    { params: seed ? { seed } : undefined },
  )
  return res.data
}

/**
 * `GET /tester/questions/{type}/{id}/answer-key/` 🔒 staff — just tell me.
 *
 * Separate from the rehearsal payload on purpose: a board that arrived with its
 * key attached would make every attempt at it a formality, including the honest
 * ones. Asking for the answer is a different request, and it looks like one.
 *
 * The pools come back in their authored order (most obvious first) rather than
 * floated around anybody's answer — there isn't one to float.
 */
export async function getTesterAnswerKeyFor(
  questionType: string,
  questionId: string,
): Promise<AnswerKey> {
  const res = await apiClient.get<AnswerKey>(
    `/tester/questions/${questionType}/${questionId}/answer-key/`,
  )
  return res.data
}

/**
 * `POST /tester/questions/{type}/{id}/answer/` 🔒 staff — mark my answer.
 *
 * `elapsedMs` is the one thing in this whole app that reports a clock to the
 * server. The real game refuses it — speed is scored, so `submit_answer`
 * measures against the server's own stamp and would reject a figure sent from
 * here. Nothing is at stake in a rehearsal (no matchup, no points that persist,
 * no ladder), and being able to ask "what would this have paid at four seconds"
 * without waiting four seconds is most of the value of one.
 */
export async function submitTesterAnswer(
  questionType: string,
  questionId: string,
  submitted: AnswerSubmission,
  elapsedMs: number,
): Promise<TesterVerdict> {
  const res = await apiClient.post<TesterVerdict>(
    `/tester/questions/${questionType}/${questionId}/answer/`,
    { submitted, elapsed_ms: Math.max(0, Math.round(elapsedMs)) },
  )
  return res.data
}
