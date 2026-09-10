/*
 * The domain, as it arrives on the wire. Hand-written rather than generated:
 * the surface is small enough to read in one sitting, and the *comments* are
 * half the value — several of these shapes carry a rule (what a payload may not
 * contain, which id a submission names) that no generator would carry with it.
 *
 * Mirrors, in order: `apps.accounts.api.serializers`, `apps.players`,
 * `apps.categories`, `apps.rankings`, `apps.achievements`, `apps.matches` and —
 * the interesting one — `apps.questions.api.serializers` /
 * `apps.questions.schemas.answers`.
 */

/* --- The envelope ---------------------------------------------------------- */

/** `meta.pagination` on every list endpoint. The client unwraps `data` itself. */
export interface Pagination {
  count: number
  page: number
  pages: number
  page_size: number
  next: string | null
  previous: string | null
}

/* --- Identity -------------------------------------------------------------- */

/**
 * `GET /auth/me/` — the caller's account. **The only payload in the whole API
 * that may carry an email address**, which is a rule the backend enforces with
 * a test that walks every serializer, and which is why nothing else in this
 * file has an `email` field.
 *
 * It also carries the player's public identity, so a signed-in client has a
 * name and an avatar without a second round trip.
 */
export interface User {
  id: string
  email: string | null
  full_name: string
  created_at: string
  player_id: string | null
  player_name: string | null
  /** True while the name is the generated placeholder — the client's cue to
   *  ask for a real one (see /welcome). Nobody else has any use for it. */
  player_name_is_auto: boolean
  player_avatar_url: string | null
}

/** `GET /auth/config/` — which sign-in methods this deployment has credentials
 *  for. Asked *before* the sign-in screen can draw itself: a tier without a
 *  password door leaves those routes unmounted (404), so a form that posted to
 *  them would fail with nothing to say. */
export interface AuthConfig {
  password_enabled: boolean
  google_enabled: boolean
}

/** What a credential exchange returns. The refresh token is deliberately absent
 *  — it rides an HttpOnly cookie the browser holds and JS never sees. */
export interface AuthTokens {
  access: string
}

/* --- The competitor -------------------------------------------------------- */

/** A player as anybody may see them: a name and a picture. Never an email. */
export interface Player {
  id: string
  display_name: string
  avatar_url: string | null
}

/** `GET/PATCH /players/me/` — the public payload plus what only they need. */
export interface PlayerMe extends Player {
  /** True while the name is still the generated one. */
  has_auto_name: boolean
  created_at: string
}

/** `GET /players/display-name-available/?display_name=…`
 *
 *  A courtesy for the sign-up screen, not a gate — the claim is settled by the
 *  PATCH and, under a race, by the database constraint underneath it. `reason`
 *  carries the refusal code (`display_name_taken`, `invalid_display_name`,
 *  `reserved_display_name`) so the field can show the same message the PATCH
 *  would have given, before anybody presses save. */
export interface DisplayNameAvailability {
  display_name: string
  available: boolean
  reason: string | null
  message: string | null
}

/** `GET /players/{display_name}/` — the public profile, in one round trip. */
export interface PlayerProfile extends Player {
  rankings: Ranking[]
  badges: PlayerAchievement[]
}

/* --- Category, ladder, badges ---------------------------------------------- */

/** A category says what a question is *about*; a question type says how it is
 *  answered, and the two are independent by design. There is no `id` here on
 *  purpose: the slug is the identifier the API takes and answers with. */
export interface Category {
  slug: string
  name: string
  description: string
}

/** One player's standing in one category. Embedded in a profile, one per
 *  category they have played. */
export interface Ranking {
  category: string
  category_name: string
  rating: number
  wins: number
  losses: number
  games_played: number
}

/** One row of `GET /rankings/{category}/` — a standing plus who holds it. */
export interface LadderEntry extends Ranking {
  player: Player
}

/** One earned badge: the catalog entry plus when this player got it. */
export interface PlayerAchievement {
  slug: string
  name: string
  description: string
  icon_url: string | null
  earned_at: string
}

/* --- Match history --------------------------------------------------------- */

export type MatchupStatus = 'waiting' | 'active' | 'completed' | 'cancelled'
/** How a finished matchup finished. Set only at a terminal status, so a live
 *  matchup has neither. `abandoned` still moved the ladder — see
 *  `apps.matches.services.abandon_matchup`. */
export type MatchupOutcome = 'played' | 'abandoned'

/** One side of the result — the score line a scoreboard shows. */
export interface MatchupPlayer {
  player: Player
  score: number
  correct_answers: number
  total_answer_time_ms: number
  is_winner: boolean
  /** When they walked; null for a match played out. */
  left_at: string | null
}

/** One row of `GET /matches/` — enough to render history without resolving
 *  every question in every past match. */
export interface MatchupSummary {
  id: string
  category: string
  question_count: number
  status: MatchupStatus
  outcome: MatchupOutcome
  started_at: string | null
  completed_at: string | null
  players: MatchupPlayer[]
}

/** One player's own submission to one question, as a box score reports it.
 *  `submitted` is the raw payload they sent — see `AnswerSubmission`. */
export interface PlayerAnswerRecord {
  submitted: AnswerSubmission
  is_correct: boolean
  /** Credit, 0.0–1.0. A matrix can be partly right, which is why this is not a
   *  boolean and why `is_correct` alone would misreport it. */
  score: number
  /** What that credit was worth once speed was applied. */
  points: number
  response_time_ms: number
  answered_at: string
}

/** One question of the match, as it was played, plus who answered what.
 *
 *  `answers` is keyed by **display name**, not by player id — that is the
 *  backend's shape (`MatchupQuestionSerializer.get_answers`), so a box score
 *  looks up its own row by name. */
export interface MatchupQuestionRecord {
  order: number
  started_at: string
  completed_at: string
  question: PlayQuestion
  answers: Record<string, PlayerAnswerRecord>
}

/** A full box score — `GET /matches/{id}/`. */
export interface MatchupDetail extends MatchupSummary {
  questions: MatchupQuestionRecord[]
}

/* --- A question, as a player is allowed to see it ---------------------------
 *
 * These mirror `apps.questions.api.serializers`, which the backend calls "the
 * anti-cheat surface". **Nothing here names a correct answer** — no
 * `is_correct`, no `answer`, no `correct_position`, no `accepted_answers` —
 * because the payload does not carry them: a serializer that declared one fails
 * at import and the backend refuses to boot.
 *
 * Two consequences worth stating on this side of the wire, because a client
 * author will otherwise look for them and conclude something is missing:
 *
 *  - A multiple-answer question does not say **how many** options are correct.
 *    A count would halve the search space on a four-option question, so the UI
 *    renders checkboxes and the player decides how many to tick.
 *  - An ordering question's options arrive **shuffled**, and the shuffle is not
 *    cosmetic: the authored order *is* the answer.
 *
 * The shuffle is per *matchup*, not per player — both sides see the same board,
 * because a race in which the two players are reading different boards is not
 * one. A reconnecting player gets the board they left rather than a new one.
 */

export type QuestionType =
  | 'single-answer'
  | 'image-answer'
  | 'multiple-answer'
  | 'true-false'
  | 'free-text'
  | 'ordering'
  | 'matrix'

/** The fields every question shows, whatever its answer shape.
 *
 *  `slug` is deliberately absent though it is the question's name everywhere in
 *  the backend: slugs are hand-authored to be readable, and
 *  `kobe-81-point-game` is a perfectly ordinary slug and a complete answer. */
interface BaseQuestion {
  id: string
  description: string
  /** 1–10. The bands are 1-3 easy, 4-7 medium, 8-10 hard. */
  level: number
  category: string
  /** An illustration of the play being asked about — most questions have none.
   *  Not to be confused with an image-answer question's *options*. */
  image: string | null
}

/** An option the player picks, and the id they pick it by. Submissions name
 *  options by id, never by text: two options worded the same are still two
 *  options, and a client must not be able to answer with text never offered. */
export interface TextOption {
  id: number
  text: string
}

export interface ImageOption {
  id: number
  image: string
  /** Alt text. It names *which* option this is, not whether it is right — so
   *  "Kobe Bryant" beside a photo of Kobe Bryant is what a screen reader needs,
   *  not a hint. Every option carries one. */
  label: string
}

/** A matrix heading, down the side or along the top. */
export interface Axis {
  id: number
  title: string
}

/** An intersection the player is asked to fill, and nothing about what goes in
 *  it. The grid is **sparse** — the authored cells are a subset of rows ×
 *  columns — so a client that drew an input in every square would have players
 *  spending the clock on squares nobody scores. */
export interface Cell {
  row_id: number
  column_id: number
}

export interface SingleAnswerQuestion extends BaseQuestion {
  type: 'single-answer'
  options: TextOption[]
}
export interface ImageAnswerQuestion extends BaseQuestion {
  type: 'image-answer'
  options: ImageOption[]
}
export interface MultipleAnswerQuestion extends BaseQuestion {
  type: 'multiple-answer'
  options: TextOption[]
}
export interface TrueFalseQuestion extends BaseQuestion {
  type: 'true-false'
}
export interface FreeTextQuestion extends BaseQuestion {
  type: 'free-text'
}
export interface OrderingQuestion extends BaseQuestion {
  type: 'ordering'
  instruction: string
  options: TextOption[]
}
export interface MatrixQuestion extends BaseQuestion {
  type: 'matrix'
  row_count: number
  column_count: number
  rows: Axis[]
  columns: Axis[]
  cells: Cell[]
}

/** A question as its two players see it, discriminated on `type`. */
export type PlayQuestion =
  | SingleAnswerQuestion
  | ImageAnswerQuestion
  | MultipleAnswerQuestion
  | TrueFalseQuestion
  | FreeTextQuestion
  | OrderingQuestion
  | MatrixQuestion

/* --- An answer, as a player submits it -------------------------------------
 *
 * Mirrors `apps.questions.schemas.answers`, and inherits its strictness: the
 * backend's pydantic models forbid unknown keys, so an extra field is a refusal
 * rather than something quietly dropped.
 *
 * There is no `response_time_ms` here and there must never be one. The server
 * measures it against its own clock — `submit_answer` does not accept a
 * client's figure, and sending one would be rejected as a malformed payload
 * rather than trusted. Speed is scored; speed is therefore not something the
 * player's device gets to report.
 *
 * `type` has to agree with the question's own type. Single-answer and
 * image-answer carry the identical body, and are still two variants for exactly
 * that reason: a client answering an image question with a text-question payload
 * is a bug, and leniency here is what would hide it until the two shapes stop
 * matching.
 */

export interface SingleAnswerSubmission {
  type: 'single-answer'
  option_id: number
}
export interface ImageAnswerSubmission {
  type: 'image-answer'
  option_id: number
}
export interface MultipleAnswerSubmission {
  type: 'multiple-answer'
  /** Every option believed correct, and no others. At least one: an empty set
   *  is not a submission — running out of time is the question *timing out*,
   *  which is the server's own path, not an answer with no picks in it. */
  option_ids: number[]
}
export interface TrueFalseSubmission {
  type: 'true-false'
  answer: boolean
}
export interface FreeTextSubmission {
  type: 'free-text'
  /** What the player typed, verbatim. Casefolding and trimming are the
   *  evaluator's business; a recorded answer should be the thing the player can
   *  be shown afterwards, not a normalized key they never wrote. */
  text: string
}
export interface OrderingSubmission {
  type: 'ordering'
  /** The whole arrangement, first to last — not the moves that produced it. */
  option_ids: number[]
}
export interface MatrixCellSubmission {
  row_id: number
  column_id: number
  answer: string
}
export interface MatrixSubmission {
  type: 'matrix'
  /** The cells filled in — not necessarily all of them. A grid is scored per
   *  cell, so a partly filled submission is a partly right answer rather than a
   *  malformed one. Two answers for one intersection *is* malformed. */
  cells: MatrixCellSubmission[]
}

export type AnswerSubmission =
  | SingleAnswerSubmission
  | ImageAnswerSubmission
  | MultipleAnswerSubmission
  | TrueFalseSubmission
  | FreeTextSubmission
  | OrderingSubmission
  | MatrixSubmission
