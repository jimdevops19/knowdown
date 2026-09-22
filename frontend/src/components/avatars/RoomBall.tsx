import { useId, type ReactNode } from 'react'

/*
 * A room's disc, redrawn as an actual ball rather than a flat-filled circle:
 * a radial gradient standing in for a curved surface, a soft occlusion
 * gradient low and center so it reads as receding toward its own edge, one
 * soft-edged specular bloom catching the top-left the way light actually
 * would, a seam ring, a drop shadow lifting it off the page. The highlight is
 * itself a radial gradient fading to transparent rather than a flat shape
 * with a hard edge — a real reflection blooms and fades, it does not end in a
 * visible boundary (an earlier cut used two opaque ellipses and read as a
 * stain rather than a sphere). Same dimensional language as the dock's icons
 * (`components/icons/navIcons.tsx`) — gradient + highlight + `feDropShadow`
 * — applied to a sphere instead of a free-standing glyph.
 *
 * Nothing is lettered across the face. A ball wears an optional `logo` badge,
 * dead center — the one spot on a sphere that reads as "on it" rather than
 * "stuck to it" at every size this renders at — and a ball given no logo is a
 * plain sphere. The room's *name* is not the ball's job: it is set under the
 * ball, in display caps, by whatever renders it (`features/play/RoomCircles`).
 * A name lettered onto the face had to shrink to fit, which made the longest
 * room name the one that read smallest — exactly backwards — and left a room
 * with a logo unable to say its name at all.
 *
 * Gradient/filter ids are per-instance (`useId`) because the lobby renders
 * several balls at once — a literal id would collide and every ball would
 * resolve to whichever instance's `<defs>` happened to land last.
 *
 * `PALETTES` is the mirror of `apps.rooms.constants.ROOM_BALL_COLOR_KEYS` —
 * see the comment above `color:` in `rooms.yaml` for where a key is picked
 * from and how the two stay in step.
 */

export type BallColor = keyof typeof PALETTES

const PALETTES = {
  // The founding four — unchanged from the first cut of this component, so
  // an already-synced room's look does not shift under it.
  orange: { light: '#ffdcb0', mid: '#ff7a14', dark: '#c4470a', rim: '#5a2003' },
  violet: { light: '#ece0ff', mid: '#b98cff', dark: '#7c4ce6', rim: '#3c1f80' },
  pink: { light: '#ffe1f4', mid: '#ff7ad9', dark: '#d43fac', rim: '#6e1a56' },
  lime: { light: '#f2ffc4', mid: '#c8f03c', dark: '#8fb824', rim: '#43590f' },
  // The rest of the 28-color set confirmed against the ball-colors artifact.
  red: { light: '#fdc4c9', mid: '#e7404e', dark: '#b40e1b', rim: '#4c060c' },
  amber: { light: '#fde5b4', mid: '#f9b11f', dark: '#b27700', rim: '#422c00' },
  gold: { light: '#fae49e', mid: '#dfb220', dark: '#8c6e0d', rim: '#251d03' },
  yellow: { light: '#fff8cc', mid: '#f5de47', dark: '#d4b802', rim: '#655801' },
  green: { light: '#93eca4', mid: '#34b24d', dark: '#186828', rim: '#08210d' },
  emerald: { light: '#86eac0', mid: '#30a675', dark: '#155b3e', rim: '#082117' },
  teal: { light: '#7de8df', mid: '#2e9e95', dark: '#13534e', rim: '#08211f' },
  cyan: { light: '#aceaf6', mid: '#35bad4', dark: '#16798d', rim: '#07262c' },
  sky: { light: '#c5e7fc', mid: '#44a7e4', dark: '#1074b1', rim: '#07314b' },
  blue: { light: '#c5d9fc', mid: '#447ee4', dark: '#104bb1', rim: '#07204b' },
  indigo: { light: '#d0d1fb', mid: '#5a5fe2', dark: '#181dbf', rim: '#0b0e5b' },
  purple: { light: '#e9c8f9', mid: '#ab4eda', dark: '#781aa8', rim: '#330b47' },
  fuchsia: { light: '#fccffc', mid: '#e755e7', dark: '#c412c4', rim: '#5d095d' },
  rose: { light: '#fdceda', mid: '#ea537b', dark: '#c70f40', rim: '#5f071f' },
  copper: { light: '#eeb5a0', mid: '#be5b37', dark: '#74321a', rim: '#210e08' },
  slate: { light: '#b2c6dc', mid: '#5f7995', dark: '#32465d', rim: '#0e141b' },
  // Orange fades.
  peach: { light: '#fae1d1', mid: '#e7a87e', dark: '#e06c1f', rim: '#7e3d11' },
  apricot: { light: '#ffe6cc', mid: '#f4a352', dark: '#dc7004', rim: '#6e3802' },
  tangerine: { light: '#ffcba3', mid: '#ff801f', dark: '#b85000', rim: '#471f00' },
  marmalade: { light: '#ffa77a', mid: '#eb550a', dark: '#8f3000', rim: '#290e00' },
  rust: { light: '#e88868', mid: '#a54627', dark: '#57210f', rim: '#230d06' },
  sunset: { light: '#fec7b9', mid: '#f06542', dark: '#c52d07', rim: '#591403' },
  honey: { light: '#fddeb0', mid: '#eca53c', dark: '#b8720a', rim: '#4e3004' },
  papaya: { light: '#fedfcd', mid: '#fb965b', dark: '#f05800', rim: '#802f00' },
} satisfies Record<string, { light: string; mid: string; dark: string; rim: string }>

/** Every key `RoomCircles` may resolve a room's authored `color` against —
 *  anything else (including blank) falls back to the position-cycled
 *  default, the same way an unknown `logo` falls back to no logo. */
export const BALL_COLOR_KEYS = Object.keys(PALETTES) as BallColor[]

type RoomBallProps = {
  color: BallColor
  /** An optional badge worn on the face. A ball without one is plain. */
  logo?: ReactNode
  className?: string
}

export function RoomBall({ color, logo, className }: RoomBallProps) {
  const gradId = useId()
  const shadeId = useId()
  const highlightId = useId()
  const shadowId = useId()
  const palette = PALETTES[color]

  return (
    <span className={['relative isolate block', className].filter(Boolean).join(' ')}>
      <svg viewBox="0 0 100 100" className="block h-full w-full" role="img" aria-hidden="true">
        <defs>
          <radialGradient id={gradId} cx="38%" cy="32%" r="78%">
            <stop offset="0%" stopColor={palette.light} />
            <stop offset="55%" stopColor={palette.mid} />
            <stop offset="100%" stopColor={palette.dark} />
          </radialGradient>
          {/* A soft occlusion gradient low and center — the thing that reads
              as "this recedes toward its own bottom edge" rather than "this
              is a flat disc with a light source." */}
          <radialGradient id={shadeId} cx="50%" cy="86%" r="62%">
            <stop offset="0%" stopColor={palette.rim} stopOpacity="0" />
            <stop offset="100%" stopColor={palette.rim} stopOpacity="0.5" />
          </radialGradient>
          {/* One soft-edged specular bloom, not two hard-edged ellipses — a
              real highlight fades into the surface, it does not end in a
              visible edge (that read as a stain rather than a reflection). */}
          <radialGradient id={highlightId} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#fff" stopOpacity="0.45" />
            <stop offset="45%" stopColor="#fff" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#fff" stopOpacity="0" />
          </radialGradient>
          <filter id={shadowId} x="-30%" y="-20%" width="160%" height="150%">
            <feDropShadow dx="0" dy="3" stdDeviation="4" floodColor={palette.rim} floodOpacity="0.55" />
          </filter>
        </defs>
        <g filter={`url(#${shadowId})`}>
          <circle cx="50" cy="49" r="46" fill={`url(#${gradId})`} />
          <circle cx="50" cy="49" r="46" fill={`url(#${shadeId})`} />
          <circle cx="50" cy="49" r="46" fill="none" stroke={palette.rim} strokeOpacity="0.4" strokeWidth="1.2" />
          <ellipse
            cx="35"
            cy="28"
            rx="22"
            ry="16"
            fill={`url(#${highlightId})`}
            transform="rotate(-30 35 28)"
          />
        </g>
      </svg>

      {logo && (
        <span className="pointer-events-none absolute inset-0 flex items-center justify-center p-[17%]">
          {logo}
        </span>
      )}
    </span>
  )
}
