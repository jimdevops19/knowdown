import { apiClient } from '../../lib/api/client'
import type {
  AnswerKey,
  AnswerSubmission,
  TesterConfig,
  TesterQuestionCard,
  TesterQuestionSource,
  TesterRehearsal,
  TesterVerdict,
  TesterWriteResult,
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

/*
 * ---- The write half ---------------------------------------------------------
 *
 * Read the backend module before changing any of these:
 * `apps.questions.services.authoring`. The short version is the part that makes
 * this surface unusual, and it is worth saying here because it changes what a
 * green toast means —
 *
 * **These do not write question rows.** Each one edits a YAML file under
 * `backend/apps/questions/resources/`, then runs the ordinary
 * `sync_questions` over that category, which is what loads the change. So a
 * question added from this page is a question added *to the repository*: it
 * appears in `git diff`, it is reviewable as text, and it survives the next
 * deploy's sync rather than being silently undone by it — which is exactly
 * what a row written straight to the database would have been.
 *
 * Both effects come back on every write (`TesterWriteResult`), and the UI says
 * both out loud. A save that wrote the file and loaded nothing is a real
 * failure mode, and one nobody would notice from a tick.
 */

/** `GET /tester/questions/{type}/{id}/source/` 🔒 staff — the authored entry.
 *
 *  What the edit form is seeded from, and deliberately **not** the catalog card
 *  or the rehearsal. The row has had its file's `time_limit_seconds` resolved
 *  into it by the loader; the entry has not. A form built from the row would
 *  send that number back as the question's own override, and every question
 *  edited here would quietly stop tracking the tempo its file sets. */
export async function getTesterQuestionSource(
  questionType: string,
  questionId: string,
): Promise<TesterQuestionSource> {
  const res = await apiClient.get<TesterQuestionSource>(
    `/tester/questions/${questionType}/${questionId}/source/`,
  )
  return res.data
}

/** `POST /tester/questions/` 🔒 staff — author a new question.
 *
 *  The category rides beside the entry rather than inside it, because it is not
 *  a field of one: a resource file states its category once at the top, and the
 *  loader refuses an entry that disagrees with the file it sits in. Which file
 *  the block lands in follows from the entry's `type`. */
export async function createTesterQuestion(
  category: string,
  entry: Record<string, unknown>,
): Promise<TesterWriteResult> {
  const res = await apiClient.post<TesterWriteResult>('/tester/questions/', {
    category,
    entry,
  })
  return res.data
}

/** `PUT …/source/` 🔒 staff — replace the block, whole.
 *
 *  A replace and not a merge, on purpose: half of a question's keys mean
 *  something by their *absence*. Dropping `time_limit_seconds` is how an entry
 *  goes back to taking its file's clock; dropping `image` is how a picture is
 *  removed. Neither can be said by sending only the keys that changed. */
export async function updateTesterQuestion(
  questionType: string,
  questionId: string,
  entry: Record<string, unknown>,
): Promise<TesterWriteResult> {
  const res = await apiClient.put<TesterWriteResult>(
    `/tester/questions/${questionType}/${questionId}/source/`,
    { entry },
  )
  return res.data
}

/** `PATCH …/source/` 🔒 staff — retire a question, or bring it back.
 *
 *  Its own call rather than a field on the update, because it is the one edit
 *  made without opening the form — the catalog has a switch on each row, and
 *  having it send the whole entry back would let a stale list revert somebody
 *  else's edit to the question it toggled.
 *
 *  Nothing is deleted, here or anywhere: a matchup that already played this
 *  question points at the row, so retiring writes `is_active: false` into the
 *  YAML and the loader carries it to the column. Writing only the column would
 *  have the next sync put the question straight back in the pool. */
export async function setTesterQuestionActive(
  questionType: string,
  questionId: string,
  isActive: boolean,
): Promise<TesterWriteResult> {
  const res = await apiClient.patch<TesterWriteResult>(
    `/tester/questions/${questionType}/${questionId}/source/`,
    { is_active: isActive },
  )
  return res.data
}
