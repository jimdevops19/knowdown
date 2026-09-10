import { hashHue } from '../lib/nameColor'

/*
 * Circular avatar.
 *
 * Every identity gets a deterministic gradient derived from its own string, so
 * a player reads as the same colour everywhere — and, during a live match,
 * *at all*: the socket sends the opponent's UUID and never their name (see
 * features/play/MatchPage), so `seed` exists to colour someone the app cannot
 * yet name. Pass the display name where there is one, the player id where there
 * isn't, and the same person keeps a stable colour either way within a screen.
 *
 * `ring` adds a glowing halo for emphasis — whose turn it is, who just scored.
 */
export function Avatar({
  name,
  seed,
  avatarUrl,
  size = 40,
  ring = false,
}: {
  /** What to show as initials, and the default colour seed. */
  name: string
  /** Colour seed, when it differs from the name — a player id, mid-match. */
  seed?: string
  /** A real uploaded/imported image. Falls back to initials when absent. */
  avatarUrl?: string | null
  size?: number
  ring?: boolean
}) {
  const hue = hashHue(seed ?? name)
  const halo = ring
    ? `0 0 0 2px hsl(${hue} 75% 60% / 0.55), 0 0 18px -2px hsl(${hue} 75% 60% / 0.6)`
    : undefined

  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={name}
        width={size}
        height={size}
        style={{ width: size, height: size, boxShadow: halo }}
        className="inline-block shrink-0 rounded-full object-cover ring-1 ring-white/10"
      />
    )
  }

  const initials =
    name
      .split(/\s+/)
      .map((word) => word[0])
      .filter(Boolean)
      .slice(0, 2)
      .join('')
      .toUpperCase() || '?'

  // A two-stop gradient in this identity's own hue, kept dark and desaturated
  // enough that white initials stay high-contrast on top of it at every hue.
  const background = `linear-gradient(135deg, hsl(${hue} 58% 34%), hsl(${(hue + 40) % 360} 62% 20%))`

  return (
    <span
      style={{ width: size, height: size, fontSize: size * 0.4, background, boxShadow: halo }}
      className="inline-flex shrink-0 items-center justify-center rounded-full font-display font-semibold text-chalk ring-1 ring-white/10"
      aria-hidden
    >
      {initials}
    </span>
  )
}
