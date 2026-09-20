import { useEffect, useState } from 'react'

/*
 * The three seconds between "you have an opponent" and the first question.
 *
 * Two players who were each staring at their own waiting screen have to arrive
 * at the same board at the same instant, thumbs ready. A match that simply
 * appeared would hand the first question to whoever happened to be looking at
 * their phone; this screen is the whistle both of them hear.
 *
 * **It costs the match nothing, because it is not extra time.** The server
 * already stamps question one's `started_at` `QUESTION_READ_DELAY_MS` into the
 * future (`apps.matches.services.start_question`) — a beat before its clock is
 * actually running. This counts that same beat down, from the server's own
 * stamp rather than from a `Date.now()` of its own, so both players see the
 * same numeral tick at the same moment and the question opens for the two of
 * them together. Nothing here decides when the match begins; it draws the
 * instant the server already chose.
 *
 * The digits are the countdown and the ring is the spinner: the numeral is what
 * a player reads, the ring is what tells them it is *moving* between numerals —
 * a bare "3" holding still for a second reads as a stall. `startsAt` of `null`
 * is the one case with nothing to count (the socket is still opening), and the
 * ring then spins alone rather than inventing a number.
 */
export function MatchupCountdown({ startsAt }: { startsAt: number | null }) {
  const [now, setNow] = useState(() => Date.now())

  // rAF rather than an interval, for `Countdown`'s reasons: the sweep is
  // redrawn every paint instead of stepping, and a backgrounded tab stops
  // spending frames on it and picks the *time* back up on return.
  useEffect(() => {
    let frame = 0
    const tick = () => {
      setNow(Date.now())
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [])

  const remainingMs = startsAt === null ? null : Math.max(0, startsAt - now)
  // Ceil, not floor: with 2.4s left the player is being counted down to three,
  // and the last numeral on screen has to be "1" rather than "0".
  const seconds = remainingMs === null ? null : Math.max(1, Math.ceil(remainingMs / 1000))
  // How far through the *current* numeral we are, so the ring empties once per
  // second rather than once per countdown — the movement is what says the next
  // digit is coming.
  const fraction = remainingMs === null ? 1 : (remainingMs % 1000) / 1000

  const radius = 54
  const circumference = 2 * Math.PI * radius

  return (
    <div
      // Fixed and opaque: "get ready" is the only thing on screen, and a player
      // reading half a question through a translucent scrim is a player who has
      // already stopped getting ready.
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-8 bg-pitch px-6 text-center motion-safe:animate-fade-in"
      role="status"
      aria-live="assertive"
    >
      <p className="font-display text-xl font-bold text-chalk sm:text-2xl">
        Your matchup is ready in
      </p>

      <div className="relative flex h-44 w-44 items-center justify-center sm:h-52 sm:w-52">
        <svg className="absolute inset-0 h-full w-full -rotate-90" viewBox="0 0 120 120" aria-hidden>
          <circle
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            strokeWidth="4"
            className="stroke-chalk/10"
          />
          <circle
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            strokeWidth="4"
            strokeLinecap="round"
            className="stroke-court"
            strokeDasharray={circumference}
            // No CSS transition on the offset, for `Countdown`'s reason: an
            // interpolated ring lags the clock it claims to be drawing.
            strokeDashoffset={circumference * (1 - fraction)}
          />
        </svg>

        {seconds === null ? (
          // Nothing to count yet — the socket is still opening. The ring is the
          // whole message here, so it turns on its own.
          <span
            aria-hidden
            className="absolute inset-0 rounded-full border-4 border-transparent border-t-court motion-safe:animate-spin"
          />
        ) : (
          <span
            // Keyed on the numeral so each one lands with its own pop — one
            // long-lived element whose text changes would swap the digits
            // silently, which is exactly the stall the ring is there to deny.
            key={seconds}
            className="nums font-display text-8xl font-bold tabular-nums text-chalk motion-safe:animate-pop-in sm:text-9xl"
          >
            {seconds}
          </span>
        )}
      </div>

      <p className="text-sm text-ash">
        {seconds === null ? 'Opening the match…' : 'Both players are in. Thumbs ready.'}
      </p>
    </div>
  )
}
