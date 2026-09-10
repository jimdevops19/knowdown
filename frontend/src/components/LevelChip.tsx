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
const BAND_STYLES = {
  easy: { label: 'Easy', className: 'border-correct/35 bg-correct/10 text-correct' },
  medium: { label: 'Medium', className: 'border-gold/35 bg-gold/10 text-gold' },
  hard: { label: 'Hard', className: 'border-wrong/35 bg-wrong/10 text-wrong' },
} as const

export function LevelChip({ level, className = '' }: { level: number; className?: string }) {
  const { label, className: tone } = BAND_STYLES[levelBand(level)]
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 font-display text-[10px] font-semibold uppercase tracking-[0.1em] ${tone} ${className}`.trim()}
    >
      {label}
    </span>
  )
}
