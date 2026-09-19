import { useEffect, useState } from 'react'

/*
 * "Is it past that moment yet?" — as a boolean that flips itself.
 *
 * The sibling of `useQuestionClock`, and deliberately not part of it: that hook
 * redraws sixty times a second because a draining bar is what it is for, and
 * everything it reports changes every frame. This one reports a *single
 * transition*, so it costs one timer and two renders — which is the whole point
 * of it being separate. The screen it gates (`PreQuestionInfo`) sits over the
 * match for a couple of seconds, and re-rendering the match behind it every
 * frame to find out whether the couple of seconds are up would be spending the
 * player's battery on a question mark.
 *
 * `instant` of null means "nothing to wait for", which reads as *passed* rather
 * than as pending: the caller has no gate, so it must not be held behind one.
 *
 * A backgrounded tab throttles the timer and the flip lands late. That is
 * acceptable here and nowhere near the clock: nothing is scored on this, and a
 * player who was in another tab for the instruction is being shown it for a
 * moment longer on their return, not given time they did not earn.
 */
export function useInstantPassed(instant: number | null): boolean {
  const [passed, setPassed] = useState(() => hasPassed(instant))
  // The gate re-arms *during render* rather than in an effect. A new instant
  // — the next question, with a screen of its own — has to be pending from the
  // very first render that knows about it; re-arming it afterwards would paint
  // one frame of the match with the screen already dismissed, which is a flash
  // of the question through the instruction that is meant to precede it. This
  // is React's own "adjusting state when a prop changes": the extra render
  // happens before the browser paints, and nothing below runs on the stale
  // value.
  const [armed, setArmed] = useState(instant)
  if (armed !== instant) {
    setArmed(instant)
    setPassed(hasPassed(instant))
  }

  useEffect(() => {
    if (hasPassed(instant) || instant === null) return
    const timer = window.setTimeout(() => setPassed(true), instant - Date.now())
    return () => window.clearTimeout(timer)
  }, [instant])

  return passed
}

function hasPassed(instant: number | null): boolean {
  return instant === null || Date.now() >= instant
}
