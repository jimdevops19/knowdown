import { useEffect, useState } from 'react'
import { QUESTION_TIME_LIMIT_MS } from '../lib/config'

/*
 * The seconds a question is open, as a number to draw with.
 *
 * **This clock decides nothing.** The server stamped the question, the server
 * closes it, and the server measures the response time it scores against its
 * own stamp. What runs here is a picture of that — which is why it is safe for
 * it to be a few tens of milliseconds out, and why nothing downstream may treat
 * `expired` as "the question is over": the question is over when a
 * `question.result` arrives. `expired` only stops this client accepting taps
 * that the server would refuse anyway.
 *
 * It ticks on `requestAnimationFrame` rather than a 100ms interval. Two
 * reasons: a bar stepping ten times a second is visibly steppy on the very
 * screen the player is staring at, and rAF is paused by the browser in a
 * backgrounded tab — so a tab left in the background stops spending battery on
 * an animation nobody can see, and catches up on the elapsed *time* (which is
 * read from the clock, not accumulated per frame) the moment it returns.
 */
export interface QuestionClock {
  /** Milliseconds left, floored at zero. */
  remainingMs: number
  /** Seconds left, one decimal — what the numeral shows. */
  remainingSeconds: number
  /** 1 at the start, 0 at the end — the width of the bar. */
  fraction: number
  /** The clock has run out on this client. Not "the question has closed". */
  expired: boolean
  /** The last few seconds, when the bar earns the right to pulse. */
  urgent: boolean
  /**
   * The read-delay window (`startedAt` in the future) has elapsed and the
   * clock is actually counting down. Callers use this to hold back anything
   * that should appear *with* the running timer — the answer options, the bar
   * itself — rather than during the beat spent reading the question.
   */
  started: boolean
}

/** When the countdown starts pulsing, in ms remaining. */
const URGENT_AT_MS = 3_000

/**
 * @param startedAt `Date.now()` when this client saw the question open, or null
 *        when no question is open — which parks the clock full and stopped,
 *        rather than at zero, so nothing between questions reads as "expired".
 * @param limitMs How long the *server* said this question stays open
 *        (`question.started`'s `time_limit_ms`). Per question, not a constant:
 *        a matrix board is authored with six times a true/false's clock, and
 *        drawing the default over it would count down to zero while the server
 *        still held the question open — the player would sit watching an empty
 *        bar, apparently waiting on their opponent. Null (no question open)
 *        falls back to the configured default purely so the parked bar has a
 *        width.
 */
export function useQuestionClock(
  startedAt: number | null,
  limitMs: number | null,
): QuestionClock {
  const limit = limitMs ?? QUESTION_TIME_LIMIT_MS
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (startedAt === null) return
    let frame = 0
    const tick = () => {
      setNow(Date.now())
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [startedAt])

  if (startedAt === null) {
    return {
      remainingMs: limit,
      remainingSeconds: limit / 1000,
      fraction: 1,
      expired: false,
      urgent: false,
      started: false,
    }
  }

  // Clamped on both ends: the lower bound stops it reading negative once the
  // clock runs out, and the upper bound is what keeps the read-delay window
  // (`startedAt` in the future — see `useMatchup`'s `seenAt`) from showing a
  // bar over-full or a numeral counting up. Nothing here draws that delay on
  // purpose; the bar just sits full and still until the clock actually starts.
  const remainingMs = Math.min(limit, Math.max(0, limit - (now - startedAt)))
  return {
    remainingMs,
    // Floored, not rounded: a clock reading "1.0s" with 40ms left has told the
    // player they have a second they do not have.
    remainingSeconds: Math.floor(remainingMs / 100) / 10,
    fraction: remainingMs / limit,
    expired: remainingMs <= 0,
    urgent: remainingMs > 0 && remainingMs <= URGENT_AT_MS,
    started: now >= startedAt,
  }
}
