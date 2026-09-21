import { useId } from 'react'

/*
 * The bottom dock's four glyphs — free-standing dimensional objects, not
 * badges on a plate: a gradient fill, a soft highlight catching the top-left,
 * a drop shadow lifting the shape off the bar. No disc behind them, so
 * "active" has to live in the surrounding chrome (the lit tile/row) rather
 * than in the icon itself — these don't take `currentColor` tinting.
 *
 * Gradient and filter ids are per-instance (`useId`) because the sidebar and
 * the phone tab bar can both have a copy of the same icon mounted at once
 * (one hidden by a `desk:`/`short:` breakpoint, not unmounted) — a literal id
 * would collide and one copy's gradient could resolve to the other's.
 */

type IconProps = { size?: number; className?: string }

function useLiftFilter() {
  const id = useId()
  return {
    id: `lift-${id}`,
    def: (
      <filter id={`lift-${id}`} x="-30%" y="-30%" width="160%" height="160%">
        <feDropShadow dx="0" dy="3" stdDeviation="3" floodColor="#04202e" floodOpacity="0.5" />
      </filter>
    ),
  }
}

export function HomeIcon({ size = 20, className }: IconProps) {
  const grad = useId()
  const lift = useLiftFilter()
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={className} role="img" aria-hidden="true">
      <defs>
        <linearGradient id={grad} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffa645" />
          <stop offset="1" stopColor="#e5650a" />
        </linearGradient>
        {lift.def}
      </defs>
      <g filter={`url(#${lift.id})`}>
        <path
          d="M12 30 L32 11 L52 30 V50 a5 5 0 0 1-5 5H17 a5 5 0 0 1-5-5 Z"
          fill={`url(#${grad})`}
        />
        <path d="M12 30 L32 11 L52 30 L45 30 L32 19 L19 30 Z" fill="#fff" opacity="0.28" />
        <rect x="26" y="35" width="12" height="17" rx="3" fill="#5a2c05" opacity="0.55" />
        <ellipse cx="21" cy="26" rx="6" ry="3.2" fill="#fff" opacity="0.22" />
      </g>
    </svg>
  )
}

export function RankingsIcon({ size = 20, className }: IconProps) {
  const grad = useId()
  const lift = useLiftFilter()
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={className} role="img" aria-hidden="true">
      <defs>
        <linearGradient id={grad} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffe27a" />
          <stop offset="1" stopColor="#dd9c14" />
        </linearGradient>
        {lift.def}
      </defs>
      <g filter={`url(#${lift.id})`}>
        <path d="M23 6 L29 6 L35 26 L28 26 Z" fill="#5fd9ff" />
        <path d="M35 6 L41 6 L29 26 L28 26 Z" fill="#2f9bd9" />
        <circle cx="32" cy="38" r="17" fill={`url(#${grad})`} />
        <circle cx="32" cy="38" r="17" fill="none" stroke="#a97a10" strokeWidth="1.4" opacity="0.45" />
        <path
          d="M32 28.5l2.7 6.2 6.7.7-5.1 4.5 1.5 6.6-5.8-3.6-5.8 3.6 1.5-6.6-5.1-4.5 6.7-.7z"
          fill="#fff7de"
          opacity="0.92"
        />
        <ellipse cx="25" cy="30" rx="6.5" ry="3.6" fill="#fff" opacity="0.3" />
      </g>
    </svg>
  )
}

export function PlayIcon({ size = 20, className }: IconProps) {
  const grad = useId()
  const lift = useLiftFilter()
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={className} role="img" aria-hidden="true">
      <defs>
        <radialGradient id={grad} cx="35%" cy="30%" r="75%">
          <stop offset="0" stopColor="#ffb35c" />
          <stop offset="1" stopColor="#e5650a" />
        </radialGradient>
        {lift.def}
      </defs>
      <g filter={`url(#${lift.id})`}>
        <circle cx="32" cy="33" r="23" fill={`url(#${grad})`} />
        <circle cx="32" cy="33" r="23" fill="none" stroke="#b64d06" strokeWidth="1.6" opacity="0.4" />
        <path d="M25 20 L48 33 L25 46 Z" fill="#fff8f0" />
        <ellipse cx="23" cy="22" rx="7.5" ry="4.2" fill="#fff" opacity="0.32" />
      </g>
    </svg>
  )
}

export function RulesIcon({ size = 20, className }: IconProps) {
  const grad = useId()
  const lift = useLiftFilter()
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={className} role="img" aria-hidden="true">
      <defs>
        <linearGradient id={grad} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#cfe6f2" />
        </linearGradient>
        {lift.def}
      </defs>
      <g filter={`url(#${lift.id})`}>
        <rect x="14" y="10" width="36" height="46" rx="7" fill={`url(#${grad})`} />
        <rect x="24" y="5" width="16" height="11" rx="4" fill="#0b1b24" />
        <rect x="27" y="8.5" width="10" height="4" rx="2" fill="#3a4c58" />
        <path d="M20 27h20M20 35h24M20 43h16" stroke="#17466a" strokeWidth="3.2" strokeLinecap="round" opacity="0.55" />
        <path
          d="M38 39l4 4 8-9"
          fill="none"
          stroke="#ff7a14"
          strokeWidth="4.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <ellipse cx="22" cy="18" rx="6.5" ry="3.4" fill="#fff" opacity="0.55" />
      </g>
    </svg>
  )
}
