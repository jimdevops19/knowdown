import { useId } from 'react'

/*
 * The mark, the badge and the wordmark lockup.
 *
 * The mark is one ball cut on the diagonal: brand orange on the upper half,
 * the logo's azure on the lower, a dark seam between them. It is the oldest
 * picture this app has of itself — two kits that never clash, your side and
 * theirs — drawn as a single object rather than as two things side by side.
 *
 * ## Why not the K, and why not the buzzer before it
 *
 * The mark has been three things. A buzzer (a dot inside a ring cut open at
 * the top right) read as a camera lens on every screen. The K that replaced it
 * solved that — a letter cannot be mistaken for an object — but it solved it by
 * saying nothing at all: a single flat-sided letter on an orange tile is the
 * shape of roughly half the app icons on a home screen, and it carried none of
 * what the product is. It was a correct mark for a company and a dull one for
 * a game.
 *
 * The ball keeps the letter's virtue (it is a shape, not a diagram, so it
 * cannot be misread as another object) and adds the thing the letter lacked:
 * it is a *match*. Two colours meeting on a hard edge is the whole premise —
 * 1v1, one clock — and it is legible the instant it is seen, at any size, in
 * any culture, without reading a word. It also finally uses the opposition the
 * design system already argued for, instead of leaving the azure to appear
 * only as a marker on a scoreboard.
 *
 * ## Three forms, and when each one is used
 *
 *   LogoMark   the ball alone, no type. Every small surface: the phone header,
 *              a browser tab, a launcher icon, an install prompt. The wordless
 *              form *is* the mark — the ball has to work at 16px, where any
 *              lettering inside it is a grey smear.
 *   LogoBadge  the ball with KNOWDOWN struck across it on a dark band. The
 *              signed piece: a doorway screen, a share image, merchandise.
 *              Needs ~72px before the band is worth reading, so it is never
 *              the one in a row of chrome.
 *   Logo       the mark with the wordmark set beside it. The lockup for
 *              anywhere with horizontal room — the sidebar, the desk header,
 *              the home hero.
 *
 * `LogoMark` and `LogoBadge` are the same drawing plus one band, which is why
 * they share `Ball` below rather than being two sets of coordinates. The badge
 * is never built by putting `<Logo>` next to the ball: the band already says
 * the name, and a lockup around it would say it twice.
 *
 * ## The geometry
 *
 * One 64-unit grid, the same grid the mascots and room logos are drawn on. The
 * numbers here are repeated in exactly two other places — `public/favicon.svg`
 * (fetched before any of this runs) and `scripts/generate_pwa_icons.py` (which
 * bakes the launcher PNGs). Change it here and change it there.
 */

/** Disc radius. Leaves room for the 1.5-wide keyline to sit inside the box. */
const R = 29.25

/*
 * The seam runs corner to corner on the anti-diagonal (x + y = 64), and both
 * halves are drawn past the edge of the box so the clip circle — not the
 * polygon — decides where the colour stops. A half traced to the ball's own
 * curve would need the arc spelled out twice and would still leave a hairline
 * of ground at some zoom levels.
 */
const UPPER_LEFT = '-8,72 72,-8 -8,-8'

function Ball({ clipId, band }: { clipId: string; band?: boolean }) {
  return (
    <>
      <defs>
        <clipPath id={clipId}>
          <circle cx="32" cy="32" r={R} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clipId})`}>
        {/* Azure first as a full disc, orange laid over its upper half: two
            polygons meeting on a shared edge leave that edge to the rasteriser,
            and it shows as a lighter line down the middle of the seam. */}
        <circle cx="32" cy="32" r={R} fill="var(--color-kit-azure)" />
        <polygon points={UPPER_LEFT} fill="var(--color-court)" />
        {/* The seam is the app's deepest ink, not a tint of either half — the
            two kits are separated by the pitch they are played on. */}
        <line x1="-8" y1="72" x2="72" y2="-8" stroke="var(--color-void)" strokeWidth="2.25" />
        {band && <rect x="-8" y="26.5" width="80" height="12" fill="var(--color-void)" />}
      </g>
      {/* A keyline in the same ink, so the ball keeps its edge on a light
          ground and simply disappears into a dark one. */}
      <circle
        cx="32"
        cy="32"
        r={R}
        fill="none"
        stroke="var(--color-void)"
        strokeWidth="1.5"
      />
    </>
  )
}

/**
 * The ball alone — the form that has to survive 16px.
 */
export function LogoMark({ size = 32, className = '' }: { size?: number; className?: string }) {
  const clipId = useId()
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden
      className={className}
    >
      <Ball clipId={clipId} />
    </svg>
  )
}

/**
 * The ball with the name struck across it.
 *
 * The wordmark is live text rather than outlines: it is set in the app's own
 * display face at the width the rest of the app is set in, so the badge
 * restyles with the type system instead of drifting away from it.
 *
 * `textLength` is what holds the setting together. The band is a fixed chord
 * of a circle, so the word has exactly one width it may be — and letting the
 * glyphs fall where they land would either overrun the ball's curve or leave
 * the name floating in the middle of a plate. Spelling the width out (and
 * letting the renderer put the difference *between* the letters, never inside
 * them) also opens the tracking, which is what the word needs at this weight:
 * eight widened caps set solid read as one long shape rather than as a name.
 */
export function LogoBadge({ size = 96, className = '' }: { size?: number; className?: string }) {
  const clipId = useId()
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      role="img"
      aria-label="knowdown"
      className={className}
    >
      <Ball clipId={clipId} band />
      <text
        x="32"
        y="35.5"
        textAnchor="middle"
        textLength="50.5"
        lengthAdjust="spacing"
        fontSize="8"
        className="font-display font-extrabold [font-stretch:115%]"
        fill="var(--color-chalk)"
      >
        KNOWDOWN
      </text>
    </svg>
  )
}

/**
 * The wordmark, with the mark in front of it.
 *
 * The mark alone names nothing — it is a ball, and a ball is a genre — so the
 * two ship together wherever there is room: the ball carries the identity, the
 * word carries the name. The mark goes alone only where there is no room for
 * the word (the phone header, a browser tab, a launcher), and those are the
 * places the reader already knows which app they opened.
 */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <div className="flex items-center gap-2 px-1">
      <LogoMark size={size} />
      {/* Widened display caps, set solid. The two halves are told apart the way
          a jersey does it: by colour, cleanly — and by the same two colours the
          ball beside them is cut from. */}
      <span className="text-headline flex items-center text-2xl leading-none">
        <span className="text-chalk">KNOW</span>
        <span className="text-court">DOWN</span>
      </span>
    </div>
  )
}
