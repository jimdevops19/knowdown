/*
 * How a knowdown mascot is drawn.
 *
 * Every mark in `marks.ts` is one call to `mascot()` and nothing else. That is
 * the whole point of this file: the *skeleton* — plate, head mass, eye spacing
 * — is written once and never moves, so forty-one different animals still read
 * as one team rather than as forty-one clip-art downloads. What a mark gets to
 * change is ears, muzzle and gear.
 *
 * Coordinates are a 64×64 grid, emitted as the body of an `<svg viewBox="0 0
 * 64 64">`. Nothing here renders on its own — `Mascot` supplies the element.
 *
 * Adding one? There is a skill for it: `.claude/skills/mascot-avatars/`.
 */

/** Outlines, pupils, mouths. Near-black rather than black, like `--color-void`. */
export const INK = '#0b1b24'

/** The whites of eyes and the light details. Matches `--color-chalk`. */
export const CHALK = '#f2fbff'

/*
 * The disc behind the animal, one step *above* the card it usually sits on
 * (`--color-raised`, not `--color-panel`). A plate in the panel colour is
 * invisible on a panel, which is where most of these appear — the ladder, a
 * box score, the profile header — and the animal would float with no edge.
 */
export const PLATE = '#17466a'

/** The four eye treatments. Spacing is fixed; only the styling varies. */
export type Eyes = 'normal' | 'wide' | 'squint' | 'dot'

export interface MascotParts {
  /** The head fill. Everything else is chosen to sit on it. */
  fur: string
  /** Drawn *behind* the head: ears, horns, antlers, a crest, a mane. */
  ears?: string
  /** Drawn on the head, under the eyes: a snout, a beak base, a face patch. */
  muzzle?: string
  /** Drawn last, over everything: nose, mouth, gear — and the ball. */
  extra?: string
  eyes?: Eyes
  /** Override the disc. Only for a mark that needs its own ground. */
  plate?: string
}

/**
 * One mascot, as SVG markup for a 64×64 viewBox.
 *
 * The eye positions are load-bearing. Two marks whose eyes sit at different
 * heights do not look like two members of the same set, they look like two
 * illustrators — so `eyes` picks a treatment and never a position.
 */
export function mascot({
  fur,
  ears = '',
  muzzle = '',
  extra = '',
  eyes = 'normal',
  plate = PLATE,
}: MascotParts): string {
  const eyeMap: Record<Eyes, string> = {
    normal: `<circle cx="25" cy="32" r="4.6" fill="${CHALK}"/><circle cx="39" cy="32" r="4.6" fill="${CHALK}"/>
             <circle cx="25.8" cy="32.4" r="2.3" fill="${INK}"/><circle cx="38.2" cy="32.4" r="2.3" fill="${INK}"/>`,
    wide: `<circle cx="24" cy="30" r="6.4" fill="${CHALK}"/><circle cx="40" cy="30" r="6.4" fill="${CHALK}"/>
           <circle cx="25" cy="31" r="2.8" fill="${INK}"/><circle cx="39" cy="31" r="2.8" fill="${INK}"/>`,
    squint: `<path d="M20 32c3-3 7-3 10 0M34 32c3-3 7-3 10 0" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`,
    dot: `<circle cx="25" cy="31" r="3" fill="${INK}"/><circle cx="39" cy="31" r="3" fill="${INK}"/>`,
  }

  return `<circle cx="32" cy="32" r="32" fill="${plate}"/>
    ${ears}
    <ellipse cx="32" cy="34" rx="19" ry="18" fill="${fur}"/>
    ${muzzle}
    ${eyeMap[eyes]}
    ${extra}`
}

/* ── The ball ──────────────────────────────────────────────────────────────
 *
 * Very small on purpose: r = 4.6 on a 64 grid, roughly a seventh of the head.
 * Held low and right, clear of the muzzle, sitting off the head's edge against
 * the plate so it never fights the face for attention.
 *
 * Be honest about the bottom of the size range: at 24px the ball is about
 * three pixels across and reads as a dot of colour, not as a basketball. That
 * is the price of "very, very small", and it is why the livery is a filter in
 * the picker — at scoreboard size the colour is the only part that survives.
 */
export type BallKind = 'orange' | 'aba' | 'white' | 'lime'

export const BALLS: Record<BallKind, { name: string; skin: string; seam: string; note: string }> = {
  orange: {
    name: 'Orange',
    skin: '#f2731c',
    seam: '#3a1603',
    note: 'The regulation ball, and the one that matches the app’s own court orange.',
  },
  aba: {
    name: 'Red-blue-white',
    skin: '#f4f7fa',
    seam: '#16306b',
    note: 'The old ABA ball: white belly, one red panel, one blue. The busiest of the four when it gets small.',
  },
  white: {
    name: 'White',
    skin: '#f7fbff',
    seam: '#6f8ea3',
    note: 'Indoor-white. The seams do the work here rather than the fill, so they are drawn in slate rather than ink.',
  },
  lime: {
    name: 'Lime',
    skin: '#cdf06a',
    seam: '#5f8f12',
    note: 'The training ball. Nothing else in the app is this colour, so it is the fastest of the four to spot on a crowded ladder.',
  },
}

/**
 * A basketball. Defaults to the held position; pass coordinates to draw one
 * at any size, which is what the picker's livery filters do.
 */
export function ball(kind: BallKind, x = 48, y = 45.5, r = 4.6): string {
  const { skin, seam } = BALLS[kind]
  // Two crescents rather than three stripes: at r = 4.6 a third panel is half
  // a pixel wide and turns the whole ball muddy.
  const panels =
    kind === 'aba'
      ? `<path d="M${x} ${y - r} A ${r} ${r} 0 0 0 ${x} ${y + r} A ${r * 0.52} ${r} 0 0 1 ${x} ${y - r} Z" fill="#d8232a"/>
         <path d="M${x} ${y - r} A ${r} ${r} 0 0 1 ${x} ${y + r} A ${r * 0.52} ${r} 0 0 0 ${x} ${y - r} Z" fill="#1a49a8"/>`
      : ''

  return `<circle cx="${x}" cy="${y}" r="${r}" fill="${skin}"/>
    ${panels}
    <g fill="none" stroke="${seam}" stroke-width="${r * 0.174}" stroke-linecap="round">
      <path d="M${x} ${y - r} V${y + r}"/>
      <path d="M${x - r} ${y} H${x + r}"/>
      <path d="M${x - r * 0.72} ${y - r * 0.72} Q ${x} ${y} ${x - r * 0.72} ${y + r * 0.72}"/>
      <path d="M${x + r * 0.72} ${y - r * 0.72} Q ${x} ${y} ${x + r * 0.72} ${y + r * 0.72}"/>
    </g>`
}

/* The paw that holds it — drawn under the ball so the ball always wins the
 * overlap, in a darker tone of the animal's own fur so it reads as its hand. */
const paw = (tone: string): string =>
  `<ellipse cx="50" cy="53.5" rx="6.2" ry="5" fill="${tone}"/>
   <path d="M46.5 55.5v3M50 56v3.2M53.5 55.5v3" stroke="${INK}" stroke-width="1.2" stroke-linecap="round" opacity="0.55" fill="none"/>`

/** Paw, then ball. Append to `extra` — it must be the last thing drawn. */
export const holding = (tone: string, kind: BallKind): string => paw(tone) + ball(kind)
