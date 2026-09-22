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

/** The mirror of `apps.rooms.constants.ROOM_LOGO_KEYS` — see the header
 *  comment above for what keeps the two in step. */
export const ROOM_LOGOS: Record<string, ComponentType<LogoProps>> = {
  tv: TVIcon,
}
