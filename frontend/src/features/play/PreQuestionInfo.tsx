import { PRE_QUESTION_INFO_MS } from '../../lib/config'

/*
 * What you are being asked to *do*, before you are asked anything.
 *
 * Most types on this board are answered the way they look — a tile is tapped,
 * a box is typed into — and for those this screen never appears. The ones it
 * exists for are the types whose control looks like every other one and means
 * something different: an ordering board's tiles are not options to choose
 * between, they are positions to assign, and a player who reads them as "pick
 * the right one" has lost the question before the clock starts. Working that
 * out from the board costs the first seconds of the round, and those are the
 * seconds the round is scored on.
 *
 * **It owns the whole screen, and that is the feature.** The instruction used
 * to be a strip above the question, where it competed with the thing it was
 * explaining and was read by nobody who was already reading the question. Alone
 * on a black screen, with the question not yet dealt, there is nothing else to
 * look at for as long as it is up.
 *
 * **It costs the player nothing.** The beat is not taken out of the read delay,
 * it is added to it: the server stamps a question carrying one of these
 * `PRE_QUESTION_INFO_MS` further out (`apps.matches.constants.read_delay_ms_for`)
 * so the reading beat that follows is still whole and the clock still starts
 * with the options. Both players are held by the same stamp, so neither is
 * shown the question first.
 *
 * The text is authored, per resource file rather than per question
 * (`pre_question_info`): "what you do with an ordering board" is a fact about
 * the answer shape, and a line that had to be written onto every entry is a
 * line that would go missing from some of them.
 */
export function PreQuestionInfo({ text }: { text: string }) {
  return (
    <div
      // Fixed and opaque, for `MatchupCountdown`'s reason: an instruction read
      // through a scrim, over a question that is already half-legible behind
      // it, is an instruction that has been skipped.
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-court-black px-6 text-center motion-safe:animate-fade-in"
      role="status"
      // Assertive: this is the only thing on screen, and a screen-reader player
      // has the same couple of seconds to hear it as everyone else has to read
      // it — queued behind whatever was being announced, it would arrive over
      // the question it is supposed to precede.
      aria-live="assertive"
    >
      <p className="font-display text-xs font-bold uppercase tracking-[0.2em] text-volt">
        Your task
      </p>

      {/* The instruction itself, at headline size. It is one short line by
          construction (the backend caps it), so it can afford to be the
          largest type in the app for two seconds. */}
      <p className="max-w-lg text-balance font-display text-3xl font-bold leading-tight text-chalk sm:text-4xl">
        {text}
      </p>

      {/* A bar draining the beat away, so the screen reads as a held moment
          rather than as something waiting to be dismissed — with no numeral,
          because this is not a clock being raced and a countdown here would
          have the player bracing for the question instead of reading the line.
          Driven by a CSS animation rather than a per-frame width: nothing is
          measured off it, so it does not need to be the truth to the
          millisecond the way `Countdown`'s bar does. */}
      <div className="h-1 w-40 overflow-hidden rounded-[2px] bg-chalk/10" aria-hidden>
        <div
          className="h-full origin-left bg-volt motion-safe:animate-task-drain motion-reduce:hidden"
          style={{ animationDuration: `${PRE_QUESTION_INFO_MS}ms` }}
        />
      </div>

      <p className="text-sm text-ash">The question is coming up…</p>
    </div>
  )
}
