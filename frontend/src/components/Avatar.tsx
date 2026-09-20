import { Mascot } from './avatars'
import { getMark } from './avatars/marks'
import { hashHue } from '../lib/nameColor'

/*
 * Circular avatar.
 *
 * Two things can fill it: the mascot the player chose, or their initials on a
 * colour derived from their name. There is no third — uploading a picture was
 * removed along with the endpoint behind it, so the app never renders an image
 * somebody else supplied.
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
  mascot,
  size = 40,
  ring = false,
}: {
  /** What to show as initials, and the default colour seed. */
  name: string
  /** Colour seed, when it differs from the name — a player id, mid-match. */
  seed?: string
  /**
   * The mascot key off the player payload, e.g. `"raptor"`.
   *
   * A key this build does not draw falls through to initials rather than
   * rendering a hole — an older client being served a newer player row is the
   * ordinary case, not an error worth showing anybody.
   */
  mascot?: string | null
  size?: number
  ring?: boolean
}) {
  const hue = hashHue(seed ?? name)
  const halo = ring
    ? `0 0 0 2px hsl(${hue} 75% 60% / 0.55), 0 0 18px -2px hsl(${hue} 75% 60% / 0.6)`
    : undefined

  // The mark itself is a disc, so it needs no fill behind it — but it keeps
  // the same ring and halo as every other avatar, because "whose turn it is"
  // has to read the same whatever is inside the circle.
  if (mascot && getMark(mascot)) {
    return (
      <span
        style={{ width: size, height: size, boxShadow: halo }}
        className="inline-flex shrink-0 overflow-hidden rounded-full ring-1 ring-chalk/10"
      >
        <Mascot mascotKey={mascot} size={size} />
      </span>
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

  // A flat fill in this identity's own hue, kept dark and desaturated enough
  // that the initials stay high-contrast on top of it at every hue.
  //
  // Flat, where this was a 135° two-stop gradient. With a dozen avatars on a
  // ladder screen, a dozen diagonal gradients is the texture that reads as
  // generated — and the second stop was never doing any work at 40px anyway.
  // The hue is already constrained to the palette's own band upstream (see
  // `hashHue`), so a solid fill lands inside the system rather than beside it.
  const background = `hsl(${hue} 42% 26%)`

  return (
    <span
      style={{ width: size, height: size, fontSize: size * 0.4, background, boxShadow: halo }}
      className="inline-flex shrink-0 items-center justify-center rounded-full font-display font-semibold text-chalk ring-1 ring-chalk/10"
      aria-hidden
    >
      {initials}
    </span>
  )
}
