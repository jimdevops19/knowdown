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
  /** The mascot they chose, as a key (`"raptor"`), or `null` for initials.
   *  Rides along for the same reason the name and the picture do — the avatar
   *  in the top-right is on every page. */
  player_mascot: string | null
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

/** A player as anybody may see them: a name, a picture, a mascot. Never an
 *  email. */
export interface Player {
  id: string
  display_name: string
  avatar_url: string | null
  /**
   * The chosen mascot, as a key — `"raptor"`, `"polar-bear"` — resolved
   * against `components/avatars`. Not a URL: the drawings ship with the
   * client, so this costs a dozen bytes on payloads that already carry a
   * player rather than an image request per row of a ladder.
   *
   * `null` means no mascot (initials), and so does a key this build does not
   * know — an older client served a newer row. Both fall back; see `Avatar`.
   */
  mascot: string | null
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

/** One category a room draws from, and the tags narrowing it. Empty
 *  `filter_tags` means the whole category is in play. */
export interface RoomCategory {
  slug: string
  name: string
  filter_tags: Record<string, string>
}

/** A **room** — the settings a match is played under, named and joinable.
 *
 *  What a player picks, in place of a category: which categories the board is
 *  drawn from, filtered by which tags, over how many questions. `id` is absent
 *  for the same reason it is on `Category` — the slug is the identifier the API
 *  takes and answers with. */
export interface Room {
  slug: string
  name: string
  description: string
  /** The match lengths this room runs; one is drawn per match, server-side. */
  question_counts: number[]
  categories: RoomCategory[]
  /** How many questions the room can currently draw from — below the shortest
   *  match it offers, the room cannot be played and the lobby says so rather
   *  than sending somebody into a queue that will refuse them. */
  question_pool_size: number
  /** Whether a match here moves a ladder. False for a room drawing from more
   *  than one category: a rating is per category and a result can only move
   *  one, so a mixed room would credit the first for questions that came from
   *  the second. Server-decided — the rule lives in `Room.is_rated` and is
   *  frozen onto the matchup as `is_ranked` when the match is created. */
  is_rated: boolean
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

/** One row of `GET /matches/{id}/participants/` — name and picture only, safe
 *  to read while the match is still live. No score: `MatchupParticipant`
 *  deliberately mirrors none of `MatchupPlayer`'s in-progress fields, because
 *  those update the moment an answer *lands* rather than when the question
 *  closes and would leak whether the opponent just got it right. */
export interface MatchupParticipant {
  player: Player
}

/** One row of `GET /matches/` — enough to render history without resolving
 *  every question in every past match. */
export interface MatchupSummary {
  id: string
  category: string
  /** The room it was played in — the settings both players joined under, as
   *  opposed to `category`, which is only the ladder the result moved. Null for
   *  a match created from a bare category (bots, fixtures, anything predating
   *  rooms), so anything offering "play again" has to cope with its absence. */
  room: string | null
  question_count: number
  status: MatchupStatus
  outcome: MatchupOutcome
  /** Whether this result moved the ladder. False for a match against a CPU
   *  opponent, and for one played in a multi-category room (`Room.is_rated`).
   *  Decided once at creation and never re-derived, so a later edit to a room
   *  cannot change what kind of game an already-played match was. */
  is_ranked: boolean
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
  /** Sudden death — a question the server added past the agreed match length
   *  because the scores were exactly level when the board ran out. It is why a
   *  three-question match can have a fourth line in its box score. */
  is_tiebreaker: boolean
  started_at: string
  completed_at: string
  question: PlayQuestion
  answers: Record<string, PlayerAnswerRecord>
  /** What was actually right. Null for a question that has not closed — which
   *  a box score never contains, since the endpoint refuses a live match, but
   *  the field is nullable because the serializer's own gate is what guarantees
   *  it and a client that assumed otherwise would be trusting the wrong layer. */
  answer_key: AnswerKey | null
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
  | 'gradual-hints'
  | 'name-as-many'

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
  /** What the player is being asked to *do*, shown alone on screen for a beat
   *  before the question appears — "Click to order from earliest to latest".
   *  Empty for most questions, which are answered the way they look and need no
   *  such screen (`apps.questions.models.BaseQuestion.pre_question_info`).
   *
   *  The beat it is shown for is *added* to the read delay by the server, not
   *  taken out of it: a question that has one is stamped
   *  `PRE_QUESTION_INFO_MS` further out, which is exactly how this client knows
   *  when to stop showing it — see `lib/config.ts`. */
  pre_question_info: string
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
/** What goes in a box, and therefore how big to draw it. */
export type AnswerFieldKind = 'text' | 'number'

/** One box a gradual-hints question asks the player to fill, and the id a
 *  submission names it by. */
export interface AnswerField {
  id: number
  label: string
  /** Text or number — authored per field on the backend
   *  (`models.AnswerFieldKind`). What it changes is the *box*: a number gets a
   *  short one and a numeric keypad, text gets a wide one. It says what sort of
   *  thing to type and nothing about the answer — in particular not how long it
   *  is, which is why the kind is authored rather than measured off the answer
   *  key. */
  kind: AnswerFieldKind
}

/**
 * The one board that is deliberately incomplete when it arrives.
 *
 * A gradual-hints question's clues are the question, and they are paid out one
 * at a time over the socket as the server's clock reaches them
 * (`hint.revealed`). What is here is only the *shape* of that reveal — how many
 * clues are coming and how far apart — which is enough to draw the waiting
 * without having been told what is being waited for.
 *
 * That split is not decoration. Waiting is what buys a clue: a player who
 * answers on the first is answering a harder question than one who waits for
 * the fifth, and is paid for it in speed. A board carrying all five would hand
 * the whole reveal to anyone with a network tab, so the backend forbids the
 * field by name and it cannot appear here either.
 */
export interface GradualHintsQuestion extends BaseQuestion {
  type: 'gradual-hints'
  /** How many clues this question will reveal, first to last. */
  hint_count: number
  /** The gap between them. The first lands when the countdown starts. */
  hint_interval_ms: number
  /** The boxes to fill, in the authored order — they are boxes, not options, so
   *  they are never shuffled. */
  answer_fields: AnswerField[]
}

/**
 * "Name as many players as you can with 1,000+ career three-pointers."
 *
 * The board with **no options at all**, and deliberately so: the answer key is
 * every qualifying player in NBA history, read at scoring time out of a baked
 * CSV on the backend (`apps.questions.career_stats`). Sending any part of it
 * would be sending the answer, so the prompt is the whole question — which is
 * why this type is authored with the stat and the line spelled out in words.
 *
 * What is here is enough to draw progress and nothing else:
 *
 *  - `target_score` is the denominator of the question's credit. A name is
 *    worth the player's fame grade, 2 (everybody says it) to 10 (a deep cut),
 *    and this is the pile that counts as a complete answer. It says how much of
 *    an answer is a full one and nothing about what is in one — the same thing
 *    a matrix's `row_count` says.
 *  - `max_names` is the cap the payload schema enforces, so the board can stop
 *    taking names before the server would refuse the list.
 *
 * **The list is submitted once, at the end.** There is no per-name verdict and
 * there must never be one: a board that asked the server about each name as it
 * was typed would be using it as a lookup, and the question would answer itself
 * by the third guess. The board accumulates locally and sends everything in one
 * `AnswerSubmission`.
 */
export interface NameAsManyQuestion extends BaseQuestion {
  type: 'name-as-many'
  /** Popularity points that count as a full answer. */
  target_score: number
  /** Which baked dataset the answers come from — a display fact (it says a
   *  client may offer NBA-player autocomplete), not a clue. */
  dataset: string
  /** The most names one submission may carry. */
  max_names: number
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
  | GradualHintsQuestion
  | NameAsManyQuestion

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

export interface AnswerFieldSubmission {
  /** By id, never by label — a client that matched labels back would make an
   *  answer depend on the exact spelling of a heading. */
  field_id: number
  text: string
}
export interface GradualHintsSubmission {
  type: 'gradual-hints'
  /** The boxes filled in — not necessarily all of them. Scored per field, so a
   *  partial answer is partly right rather than malformed; the denominator is
   *  every field the question asks for, so leaving one blank costs its share.
   *  Two answers for one field *is* malformed. */
  answer_fields: AnswerFieldSubmission[]
}

export interface NameAsManySubmission {
  type: 'name-as-many'
  /** Every name the player listed, verbatim and in the order they typed them.
   *  At least one, at most the question's `max_names`, and **no duplicates** —
   *  the board de-duplicates as names are added, so a repeat is a client bug
   *  and the backend refuses it as malformed rather than scoring it twice. */
  names: string[]
}

export type AnswerSubmission =
  | SingleAnswerSubmission
  | ImageAnswerSubmission
  | MultipleAnswerSubmission
  | TrueFalseSubmission
  | FreeTextSubmission
  | OrderingSubmission
  | MatrixSubmission
  | GradualHintsSubmission
  | NameAsManySubmission

/* --- The answer, once the question is over ----------------------------------
 *
 * Mirrors `apps.questions.api.reveal`, which is the backend's one deliberate
 * exception to everything the block above describes — and is a separate module
 * there for the same reason this is a separate section here: the difference
 * between a payload that may name an answer and one that may not should be
 * visible at the point of use, not buried in a flag.
 *
 * A key is only ever reached through `MatchupQuestionRecord`, which only exists
 * for a finished match between the two people who played it. Nothing on the
 * play path has a field of this type, and nothing should grow one.
 *
 * Two shapes recur and are worth naming up front:
 *
 *  - **Correct options arrive as ids**, never as text, because the board beside
 *    them names its options by id and matching on text would break on two
 *    options worded the same.
 *  - **A pool of accepted spellings is truncated server-side** to
 *    `accepted.length` items out of `total`. The rest are not hidden in the
 *    payload — they were never sent. A UI showing "… and 17 more" is reporting
 *    a count, which is all it has.
 */

/** A set of accepted spellings, cut to what the server was willing to publish.
 *
 *  `total` is the size of the whole pool, so `total - accepted.length` is the
 *  tail nobody gets to see. When this player answered correctly their own
 *  spelling is `accepted[0]` — the server floats it, so a UI can render the
 *  list in order and have the player's own answer lead it without knowing
 *  which one it was. */
export interface AnswerPool {
  accepted: string[]
  total: number
}

/** One intersection of a grid, and what filled it. */
export interface MatrixCellAnswerKey extends AnswerPool {
  row_id: number
  column_id: number
}

/** One box of a gradual-hints question, and what filled it. */
export interface GradualHintsFieldAnswerKey extends AnswerPool {
  field_id: number
  label: string
}

export interface OptionIdsAnswerKey {
  type: 'single-answer' | 'image-answer' | 'multiple-answer'
  /** Every option that was correct. One id for the two single-pick types; the
   *  whole set for multiple-answer, which is also the first time the client
   *  learns how many there were — the board deliberately never said. */
  option_ids: number[]
}
export interface TrueFalseAnswerKey {
  type: 'true-false'
  answer: boolean
}
export interface FreeTextAnswerKey extends AnswerPool {
  type: 'free-text'
}
export interface OrderingAnswerKey {
  type: 'ordering'
  /** The authored arrangement, first to last — the thing the board's shuffle
   *  existed to hide. */
  option_ids: number[]
}
export interface MatrixAnswerKey {
  type: 'matrix'
  cells: MatrixCellAnswerKey[]
}
export interface GradualHintsAnswerKey {
  type: 'gradual-hints'
  /** The clues, in reveal order. They reach the client here rather than on the
   *  board because waiting for them is what the question costs — and none of
   *  them is stored per match, so without this a played-out gradual-hints
   *  question would render as a row of empty slots. */
  hints: string[]
  answer_fields: GradualHintsFieldAnswerKey[]
}

/** One name the player listed, and what it paid. Zero for a name that did not
 *  qualify — which is the only way to read this question back, since a single
 *  credit figure cannot say which of twelve names was the one that missed. */
export interface NamedEntry {
  name: string
  points: number
}

/** The qualifying players this player did *not* name, capped like every other
 *  pool: `accepted` is the handful published, most obvious first, and `total`
 *  is how many they missed altogether. The rest never crossed the wire — the
 *  whole answer key here is hundreds of names. */
export interface NameAsManyAnswerKey extends AnswerPool {
  type: 'name-as-many'
  target_score: number
  /** Points collected, the numerator of the credit that was scored. */
  earned: number
  named: NamedEntry[]
}

/** What was right, discriminated on `type` — the same `type` the question
 *  beside it carries, so a key and a board that disagree is a visible bug
 *  rather than a silently mis-rendered one. */
export type AnswerKey =
  | OptionIdsAnswerKey
  | TrueFalseAnswerKey
  | FreeTextAnswerKey
  | OrderingAnswerKey
  | MatrixAnswerKey
  | GradualHintsAnswerKey
  | NameAsManyAnswerKey

/* --- The maintainers' question tester ---------------------------------------
 *
 * Mirrors `apps.tester`, a surface that exists on a tier only when
 * `TESTER_ENDPOINT_ENABLED` mounted it and answers only an `is_staff` account.
 * Everything below is therefore reachable by nobody this app ships for — which
 * is why `useTesterAccess` probes for it rather than assuming, and why a 404 on
 * the probe is the expected answer, not an error.
 *
 * Two of these types carry things the play-time payloads above deliberately do
 * not: a card names the question's `slug`, and a rehearsal of a gradual-hints
 * question carries every clue with the offset it is due at. Both are fine here
 * for the same reason — there is no opponent and no clock that matters — and
 * both would be leaks anywhere else, so they are spelled out in their own types
 * rather than widening the ones a match uses.
 */

/** One question as the tester's catalog lists it. */
export interface TesterQuestionCard {
  id: string
  type: QuestionType
  /** The name the question is authored under, and often a complete answer —
   *  which is exactly why `PlayQuestion` has no such field. */
  slug: string
  description: string
  level: number
  category: string
  category_name: string
  tags: Record<string, string>
  /** False means matchmaking will never draw it. The catalog lists these by
   *  default: "why does this never come up" is a question this page answers. */
  is_active: boolean
  /** How long this question stays open, in seconds — authored on the entry or
   *  handed down by the resource file its whole type lives in, which is why
   *  almost every question has one. Null means neither said, and it plays at
   *  the backend's ordinary ten. The resolved figure in milliseconds is
   *  `time_limit_ms` on a rehearsal. */
  time_limit_seconds: number | null
  image: string | null
}

/** One clue of a gradual-hints question, and when the server would pay it out. */
export interface TesterHint {
  index: number
  text: string
  /** Milliseconds after the clock starts. The first is 0 — the read delay has
   *  already given the player their beat. */
  offset_ms: number
}

/** One question staged for rehearsal — `GET /tester/questions/{type}/{id}/`. */
export interface TesterRehearsal extends TesterQuestionCard {
  /** The board order. Ask again with a different one to re-deal. */
  seed: string
  /** What a matchup would give this question, resolved through the same
   *  function the match engine uses. */
  time_limit_ms: number
  read_delay_ms: number
  /** The *real* play-time board — the identical payload a live socket sends,
   *  so a rehearsal cannot look right while a match looks wrong. */
  board: PlayQuestion
  /** Empty for every type but gradual-hints, whose clues arrive here because
   *  there is no socket to pay them out. */
  hints: TesterHint[]
}

/** The verdict on a rehearsed answer — `POST …/answer/`. */
export interface TesterVerdict {
  is_correct: boolean
  /** Credit, 0.0–1.0. A grid with one cell wrong is `is_correct: false` and
   *  `score: 0.89`, and the two together are usually the interesting part. */
  score: number
  /** What that credit would have paid at `elapsed_ms`, on the same curve a real
   *  match pays on. */
  points: number
  elapsed_ms: number
  time_limit_ms: number
  submitted: AnswerSubmission
  /** What was actually right — the same shape a box score's reveal uses, built
   *  by the same backend module, so the same components render it. */
  answer_key: AnswerKey
}

/** `GET /tester/config/` — the filter bar's vocabulary, and proof of entry. */
export interface TesterConfig {
  enabled: boolean
  /** Whether this deployment honours the authoring verbs — `QUESTION_TESTER_EDITABLE`
   *  on the backend. False on staging, where an edit would rewrite YAML inside
   *  the container image: lost at the next deploy and never in git. The page
   *  keeps the buttons and greys them, because "do this from local" is the
   *  answer to the question, and a missing button answers nothing. */
  editable: boolean
  question_count: number
  categories: { slug: string; name: string; question_count: number }[]
  /** Every question type, including those with nothing authored yet. */
  types: { value: QuestionType; label: string; question_count: number }[]
  /** The difficulty bands (easy/medium/hard), each carrying the level range it
   *  covers — the catalog filters on `level_min`/`level_max`, so the band is
   *  named here and cut here, and the page never hardcodes "medium is 4..7". */
  levels: {
    value: string
    label: string
    level_min: number
    level_max: number
    question_count: number
  }[]
}

/* --- Authoring, from the tester ----------------------------------------------
 *
 * The write half of `apps.tester`, and the one thing worth understanding about
 * it before reading the types: **these endpoints edit YAML files, not rows.**
 * A create appends a block to `backend/apps/questions/resources/<category>/
 * <type>.yaml`, an update rewrites one block, a deactivation writes one line —
 * and each is followed by the ordinary `sync_questions` over that category,
 * which is what puts the change in the database.
 *
 * That is why every write answers with three things rather than the updated
 * row: the row, the file, and what the load made of the file. They can
 * disagree, and the disagreement is the interesting part.
 */

/** One question as its resource file has it, which is what the form edits.
 *
 *  `entry` is deliberately untyped past `Record<string, unknown>`. The shape it
 *  must obey is pydantic's, in `apps.questions.schemas`, and a TypeScript
 *  mirror of nine discriminated variants would be a second copy of a contract
 *  that is already validated on the way in — one that would drift, and drift by
 *  *accepting* things the loader refuses. The editor knows the shape per type;
 *  the transport does not need to. */
export interface TesterQuestionSource {
  /** `nba/single-answer.yaml` — the file to look at in the diff. */
  path: string
  category: string
  entry: Record<string, unknown>
}

/** What the `sync_questions` that followed the edit did — slugs, not counts,
 *  because "which ones" is the question a surprising number answers. */
export interface TesterSyncReport {
  created: string[]
  updated: string[]
  deactivated: string[]
  /** The same sentence `manage.py sync_questions` prints. */
  summary: string
}

/** The answer to a create or an update: both effects, plus the load. */
export interface TesterWriteResult {
  question: TesterQuestionCard
  source: TesterQuestionSource
  /** `created` or `updated` — about the *block in the file*. */
  action: 'created' | 'updated'
  sync: TesterSyncReport
}
