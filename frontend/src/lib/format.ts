/** Format an ISO date string as a short local date, or '—' when null. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString()
}

/** Format an ISO timestamp as a short local date *and* time — "12 Sep · 14:30",
 *  with the year only when it isn't the current one. '—' when null/invalid. */
export function formatDateTime(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const date = d.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    ...(d.getFullYear() === now.getFullYear() ? {} : { year: 'numeric' }),
  })
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  return `${date} · ${time}`
}

/** How long ago, in words: "just now", "3h ago", "yesterday", "2 Mar". Past
 *  timestamps only — a future one falls back to the plain date, since "in 3
 *  days" never makes sense for something that already happened. */
export function timeAgo(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return '—'
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return '—'
  const minutes = Math.round((now.getTime() - then.getTime()) / 60_000)
  if (minutes < 0) return formatDate(iso)
  if (minutes < 2) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days} days ago`
  // Past a week the exact day says more than a count of weeks.
  return then.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

/**
 * A response time as the game talks about it: "1.24s".
 *
 * Two decimals, always, because these numbers are read side by side — yours
 * against your opponent's — and a column that switches between "1.2" and "1.24"
 * is a column you have to re-read. Pair it with the `nums` utility so the
 * digits don't shift width as they change.
 */
export function formatResponseTime(ms: number): string {
  return `${(ms / 1000).toFixed(2)}s`
}

/** A rating change as a signed string: "+12", "−8", "0". Uses a real minus
 *  sign, which lines up with digits in a tabular-figures font where a hyphen
 *  does not. */
export function formatDelta(delta: number): string {
  if (delta === 0) return '0'
  return delta > 0 ? `+${delta}` : `−${Math.abs(delta)}`
}

/** An integer as its English ordinal: 1 → "1st", 22 → "22nd", 13 → "13th". */
export function ordinal(n: number): string {
  const tens = n % 100
  if (tens >= 11 && tens <= 13) return `${n}th`
  switch (n % 10) {
    case 1:
      return `${n}st`
    case 2:
      return `${n}nd`
    case 3:
      return `${n}rd`
    default:
      return `${n}th`
  }
}

/**
 * The three level bands the catalog is stocked against — 1-3, 4-7, 8-10, per
 * `apps.questions.constants`. Spelled here so a difficulty chip and the backend
 * agree on where "medium" starts.
 */
export type LevelBand = 'easy' | 'medium' | 'hard'

export function levelBand(level: number): LevelBand {
  if (level <= 3) return 'easy'
  if (level <= 7) return 'medium'
  return 'hard'
}

/** A win/loss record as "12–7", with an en dash rather than a hyphen. */
export function formatRecord(wins: number, losses: number): string {
  return `${wins}–${losses}`
}

/** Win rate as a whole percentage, or '—' for a player who has not played. */
export function winRate(wins: number, gamesPlayed: number): string {
  if (gamesPlayed <= 0) return '—'
  return `${Math.round((wins / gamesPlayed) * 100)}%`
}
