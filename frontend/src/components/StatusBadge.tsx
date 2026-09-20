import type { ReactNode } from 'react'

/*
 * A small pill of status. One component rather than a class string repeated
 * across the ladder, the history list and the match header, so a tone means the
 * same thing everywhere it appears.
 *
 * The tones are the design system's vocabulary, not free colours:
 *   live    — happening right now (the brand orange, and the only tone that pulses)
 *   win     — you won (green: the same colour a right answer takes, because a
 *             won match is the same statement made about the whole match)
 *   loss    — you lost (a muted grey, deliberately: losing a ranked match is
 *             ordinary, and painting it red would make every second game feel
 *             like an error)
 *   draw    — the double tie the server leaves unbroken (plain white)
 *   off     — switched off, and not in play because of it (a deactivated
 *             question in the tester's catalog). The app's crimson, the same
 *             one a wrong answer takes: it is the only tone here that means
 *             "this is not working as intended", and it has to read that way
 *             at a glance down a list of fifty cards. Distinct from `loss`,
 *             which is grey precisely because losing a match is ordinary.
 *   neutral — everything else: a level band, a category, a count
 */
export type StatusTone = 'live' | 'win' | 'loss' | 'draw' | 'neutral' | 'warn' | 'off'

/*
 * Three of these are solid fills and four are tinted plates, and the split is
 * the point rather than a shortage of colours.
 *
 * A solid capsule of colour is the loudest small object this app can draw, so it
 * is spent only where the badge is the *news*: something is happening right now,
 * you won, or this thing is switched off and shouldn't be. The other four are
 * metadata — a draw, a loss, a category, a caveat — and metadata that shouts is
 * how a ladder of fifty rows turns into confetti. They keep the tinted plate.
 *
 * Every solid fill takes dark ink, like every other bright surface here.
 */
const TONES: Record<StatusTone, string> = {
  live: 'bg-volt text-void',
  win: 'bg-correct text-void',
  loss: 'border-2 border-chalk/14 bg-chalk/6 text-ash',
  /*
   * White, not the brand orange.
   *
   * This chip used the primary, which worked while "primary" and "live" were
   * two different colours. They are now one orange, so a DRAW chip and a LIVE
   * chip sat a single step apart — two small orange capsules that a match list
   * shows side by side, distinguishable only by reading the word. A draw is
   * also the one result that is *not* hot: nothing is happening, nobody edged
   * it. Plain white states that, and it separates cleanly from the grey of a
   * loss, which is dimmer and set in `ash`.
   */
  draw: 'border-2 border-chalk/28 bg-chalk/12 text-chalk',
  neutral: 'border-2 border-chalk/14 bg-chalk/6 text-ash',
  warn: 'border-2 border-rival/45 bg-rival/14 text-rival',
  off: 'bg-wrong text-void',
}

export function StatusBadge({
  tone = 'neutral',
  children,
  className = '',
}: {
  tone?: StatusTone
  children: ReactNode
  className?: string
}) {
  return (
    <span
      // A pill, where this was a 3px cut chip. The old comment was right that
      // this shape decides more than any other whether the UI reads as
      // broadcast furniture or as something else — and broadcast furniture was
      // the thing to get away from. A capsule is what a game uses for anything
      // that states a quantity or a status rather than doing something: a score
      // counter, a streak, a badge. It also gained a pixel of vertical padding,
      // because a pill needs a little more room inside it than a cut rectangle
      // to stop reading as a squashed tablet.
      className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 font-display text-[11px] font-bold [font-stretch:var(--display-wide)] uppercase tracking-[0.1em] ${TONES[tone]} ${className}`.trim()}
    >
      {tone === 'live' && (
        // The one dot in the app that stays a circle: a recording light is
        // round, and this is the only element pretending to be a lamp.
        // On a solid volt capsule the lamp has to be dark to be seen at all —
        // the badge is now the colour the dot used to be.
        <span
          aria-hidden
          className="h-1.5 w-1.5 rounded-full bg-void motion-safe:animate-live-pulse"
        />
      )}
      {children}
    </span>
  )
}
