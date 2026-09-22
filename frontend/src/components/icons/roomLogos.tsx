import { useId, type ComponentType } from 'react'

/*
 * Logos a `RoomBall` can wear (see `RoomBall`'s `logo` prop) — optional: a
 * room that authors none is a plain ball, and the name is under it either
 * way. Small on purpose — these render centered on the ball at
 * roughly half its diameter — so each is two or three shapes, never fine
 * detail that would vanish at that size.
 *
 * `ROOM_LOGOS` is the registry `RoomCircles.tsx` resolves a room's `logo` key
 * (authored server-side in `rooms.yaml`, see the comment above `logo:` there)
 * against. **This is the mirror of `ROOM_LOGO_KEYS` in
 * `backend/apps/rooms/constants.py`.** Adding a logo: draw it below, add it
 * here under a new key, then add that same key to `ROOM_LOGO_KEYS` — a key
 * this map does not recognise is treated as "no logo" rather than rendered
 * blank, so a mismatch between the two lists fails quietly here and loudly on
 * the next `sync_rooms`.
 */

type LogoProps = { className?: string }

/** A boxy CRT set with rabbit-ear antennas — the 2000s room's mark. */
export function TVIcon({ className }: LogoProps) {
  const grad = useId()
  return (
    <svg viewBox="0 0 64 64" width="100%" height="100%" className={className} role="img" aria-hidden="true">
      <defs>
        <linearGradient id={grad} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff8ea" />
          <stop offset="1" stopColor="#d8c9a3" />
        </linearGradient>
      </defs>
      <path
        d="M20 20 L10 9 M44 20 L54 9"
        fill="none"
        stroke="#f2fbff"
        strokeWidth="4"
        strokeLinecap="round"
      />
      <rect x="8" y="20" width="48" height="34" rx="7" fill={`url(#${grad})`} />
      <rect x="14" y="25.5" width="26" height="23" rx="3" fill="#1c3b4d" />
      <ellipse cx="21" cy="31" rx="5.5" ry="3" fill="#5fd9ff" opacity="0.5" />
      <circle cx="47" cy="30" r="3.4" fill="#1c3b4d" />
      <circle cx="47" cy="41" r="3.4" fill="#1c3b4d" />
    </svg>
  )
}

/** A basketball drawn in reverse — navy body, chalk seams. The one way a
 *  literal ball works on the All NBA room, whose own ball is orange: an
 *  orange mark on an orange sphere is no mark at all. */
export function LeagueBallIcon({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 64 64" width="100%" height="100%" className={className} role="img" aria-hidden="true">
      <circle cx="32" cy="32" r="24" fill="#1c3b4d" />
      <g fill="none" stroke="#f2fbff" strokeWidth="2.8" strokeLinecap="round">
        <circle cx="32" cy="32" r="24" />
        {/* Every seam ends at radius 22.6, not 24: a round cap adds half the
            stroke width past its endpoint, so a seam drawn to the rim reaches
            1.4 beyond it and pokes out the side. Ending short by exactly that
            half-width lands the cap on the rim's own centre line — the seam
            still meets the rim, and nothing crosses it. */}
        <path d="M32 9.4 v45.2 M9.4 32 h45.2" />
        <path d="M15.6 16.5 Q32 32 15.6 47.5 M48.4 16.5 Q32 32 48.4 47.5" />
      </g>
    </svg>
  )
}

/** A championship banner: a chalk pennant with the notched hem that reads as
 *  cloth rather than as a shield, and one star. June Basketball's mark — a
 *  trophy would have vanished into that room's gold ball. */
export function BannerIcon({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 64 64" width="100%" height="100%" className={className} role="img" aria-hidden="true">
      <path d="M13 5 h38 v45 l-19 -11 l-19 11 z" fill="#f2fbff" />
      <polygon
        points="32.00,12.00 34.65,20.14 43.21,20.14 36.28,25.17 38.93,33.31 32.00,28.27 25.07,33.31 27.72,25.17 20.79,20.14 29.35,20.14"
        fill="#1c3b4d"
      />
    </svg>
  )
}

/** A ribboned medal — two tails and a disc with an inner ring. The Awards
 *  room's mark, and the one shape on this list that says "award" with no
 *  sport attached to it. */
export function MedalIcon({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 64 64" width="100%" height="100%" className={className} role="img" aria-hidden="true">
      <path d="M16 5 h10 l8 21 -9 5 z" fill="#f2fbff" opacity="0.8" />
      <path d="M48 5 h-10 l-8 21 9 5 z" fill="#f2fbff" opacity="0.8" />
      <circle cx="32" cy="42" r="17" fill="#f2fbff" />
      <circle cx="32" cy="42" r="12" fill="none" stroke="#1c3b4d" strokeWidth="2.6" />
      <polygon
        points="32.00,34.00 33.77,39.43 39.48,39.43 34.86,42.78 36.62,48.21 32.00,44.85 27.38,48.21 29.14,42.78 24.52,39.43 30.23,39.43"
        fill="#1c3b4d"
      />
    </svg>
  )
}

/** A jersey hanging from a peg — "hang 'em up", the retirement itself rather
 *  than the player retiring. The Russell Westbrook room's mark: a room about
 *  a career ending should not be marked with a portrait of the career. */
export function HungUpJerseyIcon({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 64 64" width="100%" height="100%" className={className} role="img" aria-hidden="true">
      <g fill="none" stroke="#f2fbff" strokeWidth="3.4" strokeLinecap="round">
        <path d="M12 8 h40" />
        <path d="M32 8 v9" strokeWidth="3" />
      </g>
      <path d="M22 17 L12 23 l4 8 6 -3 v25 h20 V28 l6 3 4 -8 -10 -6 Q32 27 22 17 z" fill="#f2fbff" />
    </svg>
  )
}

/** The mirror of `apps.rooms.constants.ROOM_LOGO_KEYS` — see the header
 *  comment above for what keeps the two in step. */
export const ROOM_LOGOS: Record<string, ComponentType<LogoProps>> = {
  tv: TVIcon,
  leagueball: LeagueBallIcon,
  banner: BannerIcon,
  medal: MedalIcon,
  hungupjersey: HungUpJerseyIcon,
}
