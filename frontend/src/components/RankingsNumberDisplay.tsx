import { useId } from 'react'

/*
 * A shield-badge for a ladder position — one dimensional object per row
 * rather than a plain digit, so the podium reads as trophy hardware at a
 * glance instead of needing a caption to explain why row 2 looks special.
 *
 * The shield's neon edge and number both key off `rank`: gold/silver/bronze
 * for the podium (1/2/3), the app's own court-orange for everyone else — so
 * "not podium" still looks like it belongs to this app rather than falling
 * back to a neutral grey that reads as "unstyled".
 *
 * Gradient/filter ids are per-instance (`useId`) for the same reason as
 * `navIcons.tsx`: the same rank can be mounted more than once on a page (a
 * row's badge and, say, a share-card preview of the same row) and a literal
 * id would let one copy's gradient hijack the other's.
 */

type Tier = {
  edge: string
  edgeDim: string
  face: [string, string]
  digit: [string, string]
}

const TIERS: Record<'gold' | 'silver' | 'bronze' | 'default', Tier> = {
  gold: {
    edge: '#ffe27a',
    edgeDim: '#dd9c14',
    face: ['#3a2f0e', '#1b1505'],
    digit: ['#fff9e6', '#ffd24a'],
  },
  silver: {
    edge: '#eef5fb',
    edgeDim: '#9fb7c6',
    face: ['#2c3944', '#141c22'],
    digit: ['#ffffff', '#cbdbe6'],
  },
  bronze: {
    edge: '#f0b27a',
    edgeDim: '#b06a2e',
    face: ['#3a260f', '#1c1206'],
    digit: ['#ffe8cf', '#e0975a'],
  },
  default: {
    edge: '#ffa645',
    edgeDim: '#e5650a',
    face: ['#17466a', '#0a2637'],
    digit: ['#ffffff', '#ffa645'],
  },
}

function tierFor(rank: number) {
  if (rank === 1) return TIERS.gold
  if (rank === 2) return TIERS.silver
  if (rank === 3) return TIERS.bronze
  return TIERS.default
}

export function RankingsNumberDisplay({
  rank,
  size = 40,
  className = '',
}: {
  rank: number
  size?: number
  className?: string
}) {
  const uid = useId()
  const edgeGrad = `rnd-edge-${uid}`
  const leftGrad = `rnd-left-${uid}`
  const rightGrad = `rnd-right-${uid}`
  const digitGrad = `rnd-digit-${uid}`
  const glow = `rnd-glow-${uid}`
  const lift = `rnd-lift-${uid}`
  const tier = tierFor(rank)
  const label = String(rank)

  return (
    <svg
      viewBox="0 0 100 118"
      width={size}
      height={(size * 118) / 100}
      className={className}
      role="img"
      aria-label={`Rank ${rank}`}
    >
      <defs>
        <linearGradient id={edgeGrad} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={tier.edge} />
          <stop offset="1" stopColor={tier.edgeDim} />
        </linearGradient>
        <linearGradient id={leftGrad} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={tier.face[0]} />
          <stop offset="1" stopColor={tier.face[1]} />
        </linearGradient>
        <linearGradient id={rightGrad} x1="1" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={tier.face[1]} />
          <stop offset="1" stopColor={tier.face[0]} />
        </linearGradient>
        <linearGradient id={digitGrad} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={tier.digit[0]} />
          <stop offset="1" stopColor={tier.digit[1]} />
        </linearGradient>
        <filter id={glow} x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="2.2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id={lift} x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="3" stdDeviation="3" floodColor="#04202e" floodOpacity="0.55" />
        </filter>
      </defs>

      <g filter={`url(#${lift})`}>
        {/* thickness lip peeking out beneath the front face */}
        <path
          d="M20 8 L80 8 L96 28 L96 56 L50 116 L4 56 L4 28 Z"
          fill={tier.edgeDim}
          opacity="0.5"
        />

        {/* neon border shield */}
        <path
          d="M20 4 L80 4 L96 24 L96 52 L50 112 L4 52 L4 24 Z"
          fill="none"
          stroke={`url(#${edgeGrad})`}
          strokeWidth="4"
          strokeLinejoin="round"
          filter={`url(#${glow})`}
        />

        {/* two facets, split down the centerline for a chiseled 3D face */}
        <path d="M50 8 L22 8 L8 26 L8 51 L50 108 Z" fill={`url(#${leftGrad})`} />
        <path d="M50 8 L78 8 L92 26 L92 51 L50 108 Z" fill={`url(#${rightGrad})`} />
        <path d="M50 8 L50 108" stroke="#ffffff" strokeWidth="0.75" opacity="0.08" />

        {/* specular shine catching the top-left facet */}
        <path d="M22 8 L8 26 L8 40 L34 12 Z" fill="#ffffff" opacity="0.06" />

        <text
          x="50"
          y="68"
          textAnchor="middle"
          fontFamily="'Archivo Variable', sans-serif"
          fontWeight="800"
          fontSize={label.length > 1 ? 40 : 52}
          fill={`url(#${digitGrad})`}
          stroke={tier.edgeDim}
          strokeWidth="1.5"
          paintOrder="stroke"
        >
          {label}
        </text>
      </g>
    </svg>
  )
}
