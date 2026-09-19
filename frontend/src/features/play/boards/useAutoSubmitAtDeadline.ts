import { useEffect, useRef } from 'react'

/**
 * How long before the server closes the question a board sends what it has.
 *
 * Far enough back that the frame still lands inside the clock the *server* is
 * keeping (`submit_answer` refuses one that arrives late), close enough that it
 * costs a player nothing: the backend scores the last second of the clock at
 * the speed floor whatever the exact millisecond
 * (`apps.matches.constants.LATE_ANSWER_FLOOR_MS`, which this mirrors), so an
 * answer auto-sent at 9.0s and one sent at 9.9s are worth the same. A second is
 * the round trip plus the margin for a phone on a slow network.
 */
export const AUTO_SUBMIT_LEAD_MS = 1_000

/**
 * Send the half-built answer at the whistle, for the boards where half an
 * answer is worth something.
 *
 * Every type the server credits per part — multiple-answer, matrix,
 * gradual-hints, name-as-many — has the same failure the others cannot have: a
 * player who ticked three boxes and ran out of time scores nothing, not because
 * they did not know the answer but because they never pressed a button. The
 * all-or-nothing boards have nothing to rescue (an incomplete ordering is not a
 * partial ordering), so they do not call this.
 *
 * `build` is read through a ref rather than a dependency, so arming the timer
 * does not depend on the working answer: a timer re-armed on every keystroke is
 * a timer that fires late on the one question where somebody is typing right up
 * to the whistle. It returns `null` when there is nothing worth sending — an
 * empty set is malformed rather than a zero, so the silence is deliberate.
 */
export function useAutoSubmitAtDeadline<T>({
  deadlineAt,
  committed,
  locked,
  build,
  onAnswer,
}: {
  deadlineAt: number | null
  /** Whether this player has already submitted — nothing left to rescue. */
  committed: boolean
  locked: boolean
  build: () => T | null
  onAnswer: (submission: T) => void
}): void {
  // Written in an effect rather than during render: a ref is not rendering
  // state, and the timer that reads it only ever fires after one has committed.
  const latest = useRef(build)
  useEffect(() => {
    latest.current = build
  })

  useEffect(() => {
    if (deadlineAt === null || committed || locked) return
    const delay = deadlineAt - AUTO_SUBMIT_LEAD_MS - Date.now()
    // Already past the lead: send immediately rather than never. A board
    // mounted this late has nothing to lose by trying — the server refuses a
    // late frame, which costs the player exactly what silence would have.
    const timer = window.setTimeout(() => {
      const submission = latest.current()
      if (submission !== null) onAnswer(submission)
    }, Math.max(0, delay))
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deadlineAt, committed, locked])
}
