import { Star } from 'lucide-react'
import { levelBand, type LevelBand } from '../lib/format'

/*
 * How hard this question is, as stars.
 *
 * The raw 1-10 level is deliberately not shown. It is an authoring dial — the
 * number an editor turns when a question feels slightly off — and publishing it
 * invites players to read a precision into it that isn't there. The backend
 * already reasons in three bands (`apps.questions.constants`: 1-3 easy, 4-7
 * medium, 8-10 hard), so three is the resolution to show, and three of anything
 * is a thing you can draw rather than spell.
 *
 * ── Why stars and not the word ──────────────────────────────────────────────
 * This was an outlined pill reading EASY / MEDIUM / HARD in tracked display
 * caps. That is the shape of a status field — the same shape an admin console
 * puts around "STAGING" — and it sat directly above the question text, which
 * made the first thing a player saw in a match a piece of metadata formatted
 * like a build label.
 *
 * Stars say the identical thing without a word: one filled of three is *less*
 * than two filled of three, read at a glance and in any language, and it is the
 * notation every phone game already taught the player. The count is what
 * carries the meaning, which is why all three slots are always drawn — a lone
 * star with nothing beside it is a decoration, a lone star in three slots is a
 * measurement.
 *
 * Gold, and gold is the one reservation in the palette this bends: DESIGN.md
 * keeps it for rank. Difficulty is close enough to be honest — a three-star
 * question is worth more than a one-star — and the form keeps them apart
 * anyway, because rank is gold *fill* (a medal, a winner's plate) and this is
 * never more than three small glyphs on the page's own ground. No plate, no
 * border, no tint: the chip is gone, not restyled.
 *
 * The band name is still in the DOM for anything that cannot see the stars, and
 * the tester keeps it visible — see `showLabel`. An authoring tool is allowed to
 * look like an authoring tool, and an editor scanning for the hard questions is
 * reading a list, not playing a game.
 */
const BAND_STARS: Record<LevelBand, number> = { easy: 1, medium: 2, hard: 3 }
const BAND_LABELS: Record<LevelBand, string> = { easy: 'Easy', medium: 'Medium', hard: 'Hard' }

export function LevelChip({
  level,
  showLabel = false,
  className = '',
}: {
  level: number
  /** Print the band name beside the stars. For the tester, where difficulty is
   *  a column being scanned rather than a cue being glanced at. */
  showLabel?: boolean
  className?: string
}) {
  const band = levelBand(level)
  const filled = BAND_STARS[band]
  const label = BAND_LABELS[band]

  return (
    <span className={`inline-flex items-center gap-1 ${className}`.trim()}>
      {/* One title, on the group: three stars are one reading, and a tooltip
          per star would be three. */}
      <span className="flex items-center gap-0.5" title={`${label} — level ${level} of 10`}>
        {[0, 1, 2].map((index) => (
          <Star
            key={index}
            size={15}
            strokeWidth={2.5}
            aria-hidden
            className={
              index < filled
                ? 'fill-gold text-gold'
                : // Outline only, and faint: an empty slot has to be visible
                  // enough to count and quiet enough not to be mistaken for a
                  // filled one at a glance.
                  'fill-none text-chalk/30'
            }
          />
        ))}
      </span>
      {showLabel ? (
        <span className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-ash">
          {label}
        </span>
      ) : (
        <span className="sr-only">{label} difficulty</span>
      )}
    </span>
  )
}
