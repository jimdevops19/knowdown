import type { QuestionClock } from '../../hooks/useQuestionClock'

/*
 * The ten seconds, as a bar and a numeral.
 *
 * The single most-looked-at element in the app, so it does two things at once
 * on purpose: the bar is read peripherally (how much is left, without looking
 * away from the options) and the numeral is read directly (how much *exactly*,
 * when it starts to matter). One channel would not do — a bar alone cannot tell
 * 1.4s from 0.6s, and a numeral alone demands a glance away from the board.
 *
 * It goes from cyan to amber to red as it drains, which is a third channel, and
 * an unreliable one: colour-blind players get the width and the digits, which
 * is why those two carry the information and the colour only reinforces it.
 *
 * The bar's width is driven by an inline style rather than a CSS transition.
 * A transition would interpolate *toward* each frame's value, lagging the real
 * clock by its own duration — a bar that says there is time left after there
 * isn't. Here the value is recomputed every frame (see `useQuestionClock`), so
 * the width is always the truth as of this paint.
 */
export function Countdown({ clock, label }: { clock: QuestionClock; label?: string }) {
  const { fraction, remainingSeconds, urgent, expired } = clock

  const tone = expired
    ? 'bg-idle'
    : urgent
      ? 'bg-wrong'
      : fraction < 0.6
        ? 'bg-gold'
        : 'bg-volt'

  return (
    <div className="flex items-center gap-3">
      <div
        className="h-2 flex-1 overflow-hidden rounded-full bg-white/8"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={10}
        aria-valuenow={remainingSeconds}
        aria-valuetext={`${remainingSeconds.toFixed(1)} seconds left`}
        aria-label={label ?? 'Time left on this question'}
      >
        <div
          className={`h-full rounded-full ${tone}`}
          style={{ width: `${Math.max(0, fraction) * 100}%` }}
        />
      </div>
      <span
        // `nums` so the digits don't shift the numeral's width as they change —
        // a clock that jitters sideways is a clock that is hard to read at a
        // glance, which is the only way this one is ever read.
        className={`nums w-14 shrink-0 text-right font-display text-lg font-bold tabular-nums ${
          expired ? 'text-idle' : urgent ? 'text-wrong motion-safe:animate-clock-urgent' : 'text-chalk'
        }`}
      >
        {remainingSeconds.toFixed(1)}s
      </span>
    </div>
  )
}
