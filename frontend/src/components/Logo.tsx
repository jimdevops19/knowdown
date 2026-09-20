/*
 * The mark and the wordmark.
 *
 * The mark is the brand's own letter — a wide, flat-sided K cut out of the
 * orange tile, drawn in the same widened display voice the wordmark beside it
 * is set in. Inline SVG rather than an asset: it is four path commands, it has
 * to take the current colour in four different contexts, and shipping it as a
 * file would mean a network request on the first paint of the sign-in screen.
 *
 * ## Why not the buzzer
 *
 * This was a buzzer: a filled dot inside a ring cut open at the top right, the
 * thing you slam when you know the answer. The idea was sound and the drawing
 * was not — a dot centred in a broken ring is the diagram of a camera lens, and
 * that is what it read as on every screen, most painfully on the profile page,
 * which at the time had a camera glyph on an upload button a thumb's width
 * away. A mark whose first reading is "photo app" is not carrying the brand,
 * however good the story behind it is.
 *
 * A letter has none of that ambiguity. It cannot be mistaken for an object
 * because it is not one, it is unmistakably *this* app rather than a genre, and
 * it survives the size the mark is actually judged at: at 16px in a browser tab
 * a ring's 2.8-unit stroke and the gap in it are two or three pixels that blur
 * into a smudge, while a K's stem and arms stay separate strokes. The three
 * alternatives that were drawn and looked at beside it all failed on the same
 * test — a side-on buzzer reads as a siren, a chevron over a bar is the
 * universal download glyph, and two facing wedges collapse into a bowtie.
 *
 * The geometry is one set of numbers on a 32-unit grid, and it is repeated in
 * exactly two other places: `frontend/public/favicon.svg` (which a browser
 * fetches before any of this runs) and `scripts/generate_pwa_icons.py` (which
 * bakes the launcher PNGs). Change it here and change it there.
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
      {/* The stem, and the two arms as one path that meets it *inside* its own
          width (the arms' inner edge is x=12.2, the stem runs to 12.4). They
          overlap rather than butt together: a seam at exactly the same
          coordinate is a hairline of orange at some zoom levels on some
          renderers, and the one place it would show is the 512px launcher icon. */}
      <path d="M8 7h4.4v18H8z" fill="var(--color-void)" />
      <path d="M24.4 7L16 15.2l8.8 9.8h-5.6l-7-8.1v-1.7L19 7z" fill="var(--color-void)" />
    </svg>
  )
}

/**
 * The wordmark, with the mark in front of it.
 *
 * The mark alone would be a poor brand at this size — it is one letter, and a
 * letter on a tile is the shape half the app icons on a home screen have — so
 * the two ship together wherever the brand appears: the tile carries the
 * identity, the word carries the name. The mark goes alone only where there is
 * no room for the word (the phone header, a browser tab, a launcher), and those
 * are the places the reader already knows which app they opened. The two halves
 * stay near-touching because it is one word.
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
