import type { ReactNode } from 'react'

/*
 * A small pill of status. One component rather than a class string repeated
 * across the ladder, the history list and the match header, so a tone means the
 * same thing everywhere it appears.
 *
 * The tones are the design system's vocabulary, not free colours:
 *   live    — happening right now (cyan, and the only tone that pulses)
 *   win     — you won (gold)
 *   loss    — you lost (a muted grey, deliberately: losing a ranked match is
 *             ordinary, and painting it red would make every second game feel
 *             like an error)
 *   draw    — the double tie the server leaves unbroken
 *   neutral — everything else: a level band, a category, a count
 */
export type StatusTone = 'live' | 'win' | 'loss' | 'draw' | 'neutral' | 'warn'

const TONES: Record<StatusTone, string> = {
  live: 'border-volt/40 bg-volt/12 text-volt',
  win: 'border-gold/40 bg-gold/12 text-gold',
  loss: 'border-white/10 bg-white/5 text-ash',
  draw: 'border-court/40 bg-court/15 text-court',
  neutral: 'border-white/10 bg-white/5 text-ash',
  warn: 'border-rival/40 bg-rival/12 text-rival',
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
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-display text-[11px] font-semibold uppercase tracking-[0.08em] ${TONES[tone]} ${className}`.trim()}
    >
      {tone === 'live' && (
        <span
          aria-hidden
          className="h-1.5 w-1.5 rounded-full bg-volt motion-safe:animate-live-pulse"
        />
      )}
      {children}
    </span>
  )
}
