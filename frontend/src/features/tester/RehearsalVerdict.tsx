import { Check, Minus, X, Zap } from 'lucide-react'
import { Card } from '../../components/Card'
import { formatResponseTime } from '../../lib/format'
import type { TesterVerdict } from '../../lib/api/types'

/*
 * How the server marked it — all four numbers, not a tick.
 *
 * `QuestionVerdict` (the live one) shows a player what happened: right or
 * wrong, how fast, what it paid. This shows a maintainer *how the grading
 * arrived there*, which is a different set of facts and a wider one:
 *
 *  · **verdict and credit, separately.** They disagree on exactly one shape —
 *    a partly-filled grid is `is_correct: false` with a score of 0.6 — and that
 *    disagreement is the single most common thing worth knowing about a matrix
 *    question. A tick alone would report it as simply wrong.
 *  · **the clock it was scored against.** Points here are what the same curve
 *    a real match uses would have paid at this elapsed time, so the elapsed
 *    time has to be visible or the points are a number from nowhere.
 *
 * Toned by the verdict, with the same three-way palette the rest of the app
 * uses for it (`correct` / `gold` for partial / `wrong`), because a maintainer
 * reading forty of these in a row is reading the colour first.
 */
export function RehearsalVerdict({ verdict }: { verdict: TesterVerdict }) {
  const partial = !verdict.is_correct && verdict.score > 0

  const tone = verdict.is_correct
    ? { border: 'border-correct/40', text: 'text-correct', label: 'Correct', Icon: Check }
    : partial
      ? { border: 'border-gold/40', text: 'text-gold', label: 'Partly right', Icon: Minus }
      : { border: 'border-wrong/40', text: 'text-wrong', label: 'Wrong', Icon: X }

  return (
    <Card border={tone.border} className="flex flex-wrap items-center gap-x-6 gap-y-3 p-4">
      <span className={`flex items-center gap-2 font-display font-bold ${tone.text}`}>
        <tone.Icon size={18} aria-hidden />
        {tone.label}
      </span>

      <Figure label="Credit" value={`${Math.round(verdict.score * 100)}%`} />
      <Figure
        label="Answered at"
        value={`${formatResponseTime(verdict.elapsed_ms)} / ${formatResponseTime(
          verdict.time_limit_ms,
        )}`}
      />
      <Figure
        label="Points"
        value={
          <span className="flex items-center gap-1">
            {verdict.points > 0 && <Zap size={14} className="text-gold" aria-hidden />}
            {verdict.points}
          </span>
        }
      />
    </Card>
  )
}

function Figure({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <span className="flex flex-col">
      <span className="font-display text-[10px] font-bold uppercase tracking-[0.12em] text-ash">
        {label}
      </span>
      <span className="nums font-display text-base font-bold text-chalk">{value}</span>
    </span>
  )
}
