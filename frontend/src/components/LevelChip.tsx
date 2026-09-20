import { levelBand } from '../lib/format'

/*
 * How hard this question was, as one of the three bands the catalog is stocked
 * against (`apps.questions.constants`: 1-3 easy, 4-7 medium, 8-10 hard).
 *
 * The raw 1-10 level is deliberately not shown. It is an authoring dial — the
 * number an editor turns when a question feels slightly off — and publishing it
 * invites players to read a precision into it that isn't there. Three bands is
 * the resolution the backend itself reasons in, so it is the resolution to show.
 */
/*
 * Tinted plates, not solid fills, and a pill rather than a cut chip. Difficulty
 * is metadata on a question card — it is never the reason you are looking at the
 * card — so it takes the quiet half of the badge vocabulary (see StatusBadge,
 * which makes the same split for the same reason).
 */
const BAND_STYLES = {
  easy: { label: 'Easy', className: 'border-correct/40 bg-correct/12 text-correct' },
  medium: { label: 'Medium', className: 'border-gold/40 bg-gold/12 text-gold' },
  hard: { label: 'Hard', className: 'border-wrong/40 bg-wrong/12 text-wrong' },
} as const

export function LevelChip({ level, className = '' }: { level: number; className?: string }) {
  const { label, className: tone } = BAND_STYLES[levelBand(level)]
  return (
    <span
      className={`inline-flex items-center rounded-pill border-2 px-2.5 py-0.5 font-display text-[10px] font-semibold uppercase tracking-[0.1em] ${tone} ${className}`.trim()}
    >
      {label}
    </span>
  )
}
