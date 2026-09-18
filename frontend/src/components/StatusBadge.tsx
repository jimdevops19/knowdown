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

const TONES: Record<StatusTone, string> = {
  live: 'border-volt/40 bg-volt/12 text-volt',
  win: 'border-correct/40 bg-correct/12 text-correct',
  loss: 'border-chalk/10 bg-chalk/5 text-ash',
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
  draw: 'border-chalk/25 bg-chalk/10 text-chalk',
  neutral: 'border-chalk/10 bg-chalk/5 text-ash',
  warn: 'border-rival/40 bg-rival/12 text-rival',
  off: 'border-wrong/45 bg-wrong/12 text-wrong',
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
      // A cut chip, not a pill. This is the label that appears most often in
      // the app — on every ladder row and every history entry — so its shape
      // does more than any other to set whether the UI reads as broadcast
      // furniture or as a row of tags on a blog.
      className={`inline-flex items-center gap-1.5 rounded-[3px] border px-2 py-0.5 font-display text-[11px] font-bold [font-stretch:var(--display-wide)] uppercase tracking-[0.1em] ${TONES[tone]} ${className}`.trim()}
    >
      {tone === 'live' && (
        // The one dot in the app that stays a circle: a recording light is
        // round, and this is the only element pretending to be a lamp.
        <span
          aria-hidden
          className="h-1.5 w-1.5 rounded-full bg-volt motion-safe:animate-live-pulse"
        />
      )}
      {children}
    </span>
  )
}
