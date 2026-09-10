/*
 * The mark and the wordmark.
 *
 * The mark is a buzzer — the thing you slam when you know the answer — drawn as
 * a filled dot inside a ring, with the ring cut open at the top right so it
 * reads as a button being pressed rather than as a generic target. Inline SVG
 * rather than an asset: it is a dozen path commands, it has to take the current
 * colour in four different contexts, and shipping it as a file would mean a
 * network request on the first paint of the sign-in screen.
 */
export function LogoMark({ size = 32, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden
      className={className}
    >
      <defs>
        <linearGradient id="kd-mark" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--color-court)" />
          <stop offset="1" stopColor="var(--color-volt)" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#kd-mark)" />
      {/* The ring, open at the top right — the gap is what makes it a buzzer
          rather than a bullseye, and it points at the corner the "down" of the
          wordmark falls toward. */}
      <path
        d="M23.5 9.5a9.5 9.5 0 1 0 2.2 4.2"
        stroke="var(--color-void)"
        strokeWidth="2.6"
        strokeLinecap="round"
        opacity="0.9"
      />
      <circle cx="16" cy="16" r="4.4" fill="var(--color-void)" opacity="0.9" />
    </svg>
  )
}

/**
 * The wordmark, with the mark in front of it.
 *
 * The mark alone would be a poor brand at this size — it is a circle, and
 * circles are everywhere — so the two ship together wherever the brand appears:
 * the tile carries the identity, the word carries the name. The two halves stay
 * near-touching because it is one word.
 */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <div className="flex items-center gap-2 px-1">
      <LogoMark size={size} />
      <span className="flex items-center font-display text-2xl font-bold tracking-tight">
        <span className="text-chalk">know</span>
        <span className="text-volt" style={{ textShadow: '0 0 18px rgba(34,211,238,0.5)' }}>
          down
        </span>
      </span>
    </div>
  )
}
