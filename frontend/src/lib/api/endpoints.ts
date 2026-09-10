import { apiClient } from './client'
import type {
  Category,
  DisplayNameAvailability,
  LadderEntry,
  MatchupDetail,
  MatchupSummary,
  Pagination,
  PlayerMe,
  PlayerProfile,
} from './types'

/*
 * Thin typed wrappers around the REST surface, grouped by backend app. One
 * function per endpoint, and nothing else: no caching policy (that is
 * `lib/query`), no error handling (the client normalizes), no React.
 *
 * The auth endpoints deliberately do *not* live here — they belong to the auth
 * feature and sit in `features/auth/api.ts`, the way the backend keeps identity
 * in its own app rather than in a shared module.
 *
 * **Everything the game itself does is missing from this file, and that is the
 * design.** Finding an opponent, seeing a question, answering it and learning
 * the result all happen over the socket (`lib/realtime/`), because the server's
 * clock is the thing being raced and a REST round trip is not a clock. What
 * REST answers here is the past (history, profiles, ladders) and the catalog —
 * never a move.
 */

/** A paginated list, as a hook wants it: the rows, and where they sit. */
export interface Page<T> {
  results: T[]
  pagination?: Pagination
}

/* --- categories ------------------------------------------------------------ */

/** `GET /categories/` 🔓 — every category a match can be played in. */
export async function listCategories(): Promise<Category[]> {
  const res = await apiClient.get<Category[]>('/categories/')
  return res.data
}

/** `GET /categories/{slug}/` 🔓 */
export async function getCategory(slug: string): Promise<Category> {
  const res = await apiClient.get<Category>(`/categories/${slug}/`)
  return res.data
}

/* --- players --------------------------------------------------------------- */

/** `GET /players/me/` 🔒 — the caller's own competitor. */
export async function getMyPlayer(): Promise<PlayerMe> {
  const res = await apiClient.get<PlayerMe>('/players/me/')
  return res.data
}

/**
 * `PATCH /players/me/` 🔒 — claim or correct the display name.
 *
 * The name is written by `services.set_display_name` and nowhere else; the
 * serializer field is read-only precisely so no payload can route around the
 * validator. Uniqueness is case-insensitive and enforced by a database
 * constraint as well, so renaming to your own capitalisation is legal and a
 * race between two claims is a `conflict`, not a 500.
 */
export async function setMyDisplayName(displayName: string): Promise<PlayerMe> {
  const res = await apiClient.patch<PlayerMe>('/players/me/', { display_name: displayName })
  return res.data
}

/**
 * `PATCH /players/me/` 🔒 — set or remove the avatar.
 *
 * Multipart, and `null` is how a picture is *removed*: an `avatar` key holding
 * nothing clears it, while a PATCH that never mentions it leaves the existing
 * one alone. The Content-Type header is deleted rather than set, so the browser
 * writes its own with the multipart boundary — setting it by hand produces a
 * body Django cannot parse, with no error that says so.
 */
export async function setMyAvatar(image: File | null): Promise<PlayerMe> {
  const form = new FormData()
  form.append('avatar', image ?? '')
  const res = await apiClient.patch<PlayerMe>('/players/me/', form, {
    headers: { 'Content-Type': undefined },
  })
  return res.data
}

/**
 * `GET /players/display-name-available/` 🔒 — can I have this name?
 *
 * Authenticated on purpose: unauthenticated, it would be a way to enumerate
 * which names exist. It answers about a *name*, never about a person — "taken"
 * says a row holds it and nothing about who.
 */
export async function checkDisplayName(displayName: string): Promise<DisplayNameAvailability> {
  const res = await apiClient.get<DisplayNameAvailability>('/players/display-name-available/', {
    params: { display_name: displayName },
  })
  return res.data
}

/** `GET /players/{display_name}/` 🔓 — anybody's public profile: name, picture,
 *  a rating per category played, and every badge earned. One round trip.
 *
 *  Looked up case-insensitively, the way the uniqueness constraint behind the
 *  name is, so `/players/Kobe` and `/players/kobe` cannot be two people. */
export async function getPlayerProfile(displayName: string): Promise<PlayerProfile> {
  const res = await apiClient.get<PlayerProfile>(`/players/${encodeURIComponent(displayName)}/`)
  return res.data
}

/* --- rankings -------------------------------------------------------------- */

/** `GET /rankings/{category}/` 🔓 — the ladder, paginated, best first. */
export async function getLadder(
  category: string,
  params: { page?: number; page_size?: number } = {},
): Promise<Page<LadderEntry>> {
  const res = await apiClient.get<LadderEntry[]>(`/rankings/${category}/`, { params })
  return { results: res.data, pagination: res.meta?.pagination }
}

/* --- matches (history only — see the note at the top) ---------------------- */

/** `GET /matches/` 🔒 — the caller's own **finished** matches, newest first.
 *
 *  A match in progress is not in here. Its row would carry both sides' running
 *  `score` and `correct_answers`, and the backend increments those the moment
 *  an answer lands rather than when the question closes — so polling this
 *  during an open question would report whether the *opponent's* answer was
 *  right, which is exactly what `player.answered` refuses to say. */
export async function listMyMatches(
  params: { page?: number; page_size?: number } = {},
): Promise<Page<MatchupSummary>> {
  const res = await apiClient.get<MatchupSummary[]>('/matches/', { params })
  return { results: res.data, pagination: res.meta?.pagination }
}

/**
 * `GET /matches/{id}/` 🔒 — the full box score of a **finished** match.
 *
 * Scoped to its two players: a matchup is a private result between them, and
 * anyone else asking gets a 403. What it adds over the list row is each
 * question as it was played — the very same board the players saw, through the
 * same play-time serializer, so a box score inherits the anti-cheat guarantee
 * rather than re-deciding it — plus each side's own submission and verdict.
 *
 * **Never call this while a match is live.** It answers 409
 * (`matchup_in_progress`), because a player *is* a party to their own live
 * match and every ownership check would otherwise pass while handing them the
 * questions they have not been asked yet and the opponent's answer to the one
 * that is open. Mid-match state comes from the socket, and only from there;
 * the summary screen calls this after `match.completed`, by which point the
 * server has already committed the matchup as completed.
 */
export async function getMatch(matchupId: string): Promise<MatchupDetail> {
  const res = await apiClient.get<MatchupDetail>(`/matches/${matchupId}/`)
  return res.data
}
