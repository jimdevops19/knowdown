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
      {/* A flat orange tile, cut to the shape scale rather than pillowed.
          This was a violet→cyan diagonal gradient — the app's logo was itself
          the clearest statement of the look the design system has moved off,
          and a two-stop diagonal gradient on a rounded square is the most
          copied logo form there is. One solid colour is both stronger at 24px
          in a tab bar and honest about the palette: the brand *is* the orange. */}
      <rect width="32" height="32" rx="5" fill="var(--color-court)" />
      {/* The ring, open at the top right — the gap is what makes it a buzzer
          rather than a bullseye, and it points at the corner the "down" of the
          wordmark falls toward. Full-strength ink, not 90%: the fill underneath
          it is bright enough to take it, and a faded mark at favicon size just
          looks unrendered. */}
      <path
        d="M23.5 9.5a9.5 9.5 0 1 0 2.2 4.2"
        stroke="var(--color-void)"
        strokeWidth="2.8"
        strokeLinecap="round"
      />
      <circle cx="16" cy="16" r="4.4" fill="var(--color-void)" />
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
      {/* Widened display caps, set solid. The second half carried a blurred
          cyan text-shadow before — neon glow on a wordmark is decoration that
          smears the letterforms at exactly the sizes a wordmark is read at, and
          it is the same halo the rest of the system dropped. The two halves are
          now told apart the way a jersey does it: by colour, cleanly. */}
      <span className="text-headline flex items-center text-2xl leading-none">
        <span className="text-chalk">KNOW</span>
        <span className="text-court">DOWN</span>
      </span>
    </div>
  )
}
