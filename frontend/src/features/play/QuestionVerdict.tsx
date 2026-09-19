import type { ReactNode } from 'react'
import { Clock, Minus, Trophy } from 'lucide-react'
import type { QuestionResultEntry } from '../../lib/realtime'
import { formatResponseTime } from '../../lib/format'

/*
 * What just happened, in the second or two between a question closing and the
 * next one opening.
 *
 * It is a strip under the board rather than a modal over it, on purpose. The
 * next question can arrive at any moment — the server opens it as soon as this
 * one closes — and a dialog that has to be dismissed would still be on screen
 * when the clock on the next question had already started. Nothing here waits
 * for a tap, and nothing here covers the board.
 *
 * **Three outcomes, not two.** A player who ran out of time has no entry in the
 * results at all, which is how the server distinguishes "didn't answer" from
 * "answered wrong" — and the difference matters to a player, because one of
 * them is a mistake and the other is a habit. So a missing entry reads as "out
 * of time", not as a wrong answer.
 *
 * **No points.** What each answer was *worth* is withheld for the same reason
 * the running total on the scoreboard is (`LiveScoreboard`): a per-question
 * "+7" is a total in instalments, and a player adding them up as they go is
 * playing the scoreboard rather than the question. The verdict — right, partly
 * right, wrong, or out of time — and how long it took are feedback on the
 * answer itself, so those stay. The points all land at the end.
 */
export function QuestionVerdict({
  results,
  myPlayerId,
  opponentName,
}: {
  results: QuestionResultEntry[]
  myPlayerId: string | null
  /** From `GET /matches/{id}/participants/`; "Rival" while that's in flight. */
  opponentName: string
}) {
  const mine = results.find((entry) => entry.player_id === myPlayerId) ?? null
  const theirs = results.find((entry) => entry.player_id !== myPlayerId) ?? null

  return (
    <div
      // `polite`, not `assertive`: it should be read after whatever the board
      // is saying, not cut across it — and it will be replaced by the next
      // question within seconds either way.
      role="status"
      aria-live="polite"
      className="flex flex-col gap-2 motion-safe:animate-slide-up"
    >
      <Row label="You" entry={mine} emphasis />
      <Row label={opponentName} entry={theirs} />
    </div>
  )
}

function Row({
  label,
  entry,
  emphasis = false,
}: {
  label: string
  entry: QuestionResultEntry | null
  emphasis?: boolean
}) {
  // No entry means the clock ran out on them — see the note above.
  if (!entry) {
    return (
      <Shell
        tone="border-chalk/8 bg-panel/60"
        label={label}
        emphasis={emphasis}
        verdict={
          <span className="flex items-center gap-1.5 text-sm text-idle">
            <Clock size={15} aria-hidden />
            Out of time
          </span>
        }
      />
    )
  }

  // `score` is credit (0.0–1.0) and `is_correct` is the verdict — two numbers
  // because a matrix can be partly right, where `is_correct` is false and the
  // credit is 0.6. Reporting only the boolean would tell a player they got a
  // grid "wrong" while paying them for most of it.
  const partial = !entry.is_correct && entry.score > 0
  const tone = entry.is_correct
    ? 'border-correct/40 bg-correct/10'
    : partial
      ? 'border-gold/40 bg-gold/10'
      : 'border-wrong/40 bg-wrong/10'

  return (
    <Shell
      tone={tone}
      label={label}
      emphasis={emphasis}
      verdict={
        <span className="flex items-center gap-2.5 text-sm">
        {entry.is_correct ? (
          <span className="flex items-center gap-1.5 font-semibold text-correct">
            <Trophy size={15} aria-hidden />
            Correct
          </span>
        ) : partial ? (
          <span className="flex items-center gap-1.5 font-semibold text-gold">
            <Minus size={15} aria-hidden />
            {Math.round(entry.score * 100)}% right
          </span>
        ) : (
          <span className="font-semibold text-wrong">Wrong</span>
        )}
          <span className="nums text-ash">{formatResponseTime(entry.response_time_ms)}</span>
        </span>
      }
    />
  )
}

/** The row's frame: who it is about on the left, how they did on the right.
 *  Split out so the "out of time" case and the scored case cannot drift apart
 *  in spacing — they sit directly above one another. */
function Shell({
  tone,
  label,
  emphasis,
  verdict,
}: {
  tone: string
  label: string
  emphasis: boolean
  verdict: ReactNode
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-tile border px-3.5 py-2.5 ${tone} ${
        emphasis ? '' : 'opacity-90'
      }`}
    >
      <span className="flex min-w-0 items-center gap-3">
        <span className="w-14 shrink-0 truncate font-display text-xs font-bold uppercase tracking-wider text-ash">
          {label}
        </span>
        {verdict}
      </span>
    </div>
  )
}
