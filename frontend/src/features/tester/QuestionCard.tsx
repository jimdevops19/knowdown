import { Link } from 'react-router-dom'
import { EyeOff, Image as ImageIcon, Timer } from 'lucide-react'
import { Card } from '../../components/Card'
import { LevelChip } from '../../components/LevelChip'
import { StatusBadge } from '../../components/StatusBadge'
import type { TesterQuestionCard } from '../../lib/api/types'

/*
 * One question in the catalog, as a card you can click into and play.
 *
 * ## The card is in two halves, and the rule is the divider
 *
 * Above the hairline: **what this question is** — its type, its band, its
 * category, and whether it is live. Below it: **the question itself**, in the
 * app's ordinary reading colour, followed by the slug it is authored under.
 *
 * That split is the whole point of the layout. A maintainer scanning fifty of
 * these is doing one of two things — looking for a *kind* of question ("the
 * grids", "the hard NBA ones") or looking for a *particular* one ("the Kobe 81
 * one") — and the two searches read different halves of the card. Mixing the
 * labels into the text, which is what a single line of chips beside a heading
 * does, makes both searches read the whole card.
 *
 * The labels are also deliberately not the question's own voice: they are set
 * small, in caps, in the muted tone this app uses for *labels about* a thing
 * (`SectionHeading`, `StatusBadge`), so the only sentence on the card that
 * looks like a sentence is the one a player would be asked.
 *
 * ## What it says that a player's screen never would
 *
 * The slug, and the inactive badge. Both are backend facts — the name in the
 * YAML, and whether matchmaking will ever draw it — and both are the answer to
 * the two questions this page exists for: "which file do I edit?" and "why does
 * this never come up?"
 */
export function QuestionCatalogCard({
  question,
  typeLabel,
}: {
  question: TesterQuestionCard
  /** The human name of the answer shape, from `GET /tester/config/` — the
   *  backend's own `QuestionType` label rather than a second copy of the eight
   *  names maintained over here. */
  typeLabel: string
}) {
  return (
    <Card
      as={Link}
      to={`/tester/${question.type}/${question.id}`}
      interactive
      edge={question.is_active ? 'court' : undefined}
      className={`flex flex-col ${question.is_active ? '' : 'opacity-75'}`}
    >
      {/* --- What it is -------------------------------------------------- */}
      <div className="flex flex-wrap items-center gap-2 border-b border-chalk/8 px-4 py-3">
        <span className="font-display text-[10px] font-bold uppercase tracking-[0.12em] text-volt">
          {typeLabel}
        </span>
        <LevelChip level={question.level} />
        <StatusBadge>{question.category_name}</StatusBadge>
        {!question.is_active && (
          <StatusBadge tone="off" className="inline-flex items-center gap-1">
            <EyeOff size={11} aria-hidden />
            Inactive
          </StatusBadge>
        )}
      </div>

      {/* --- What it asks ------------------------------------------------ */}
      <div className="flex flex-1 flex-col gap-2.5 px-4 py-3.5">
        <p className="line-clamp-3 text-sm leading-relaxed text-chalk">{question.description}</p>

        <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 pt-1">
          {/* Monospace, because a slug is an identifier to be copied into a
              file search, not prose. */}
          <code className="truncate font-mono text-[11px] text-ash">{question.slug}</code>
          {question.time_limit_seconds !== null && (
            <span className="nums flex items-center gap-1 text-[11px] text-ash">
              <Timer size={11} aria-hidden />
              {question.time_limit_seconds}s
            </span>
          )}
          {question.image && (
            <span className="flex items-center gap-1 text-[11px] text-ash">
              <ImageIcon size={11} aria-hidden />
              illustrated
            </span>
          )}
          {Object.entries(question.tags).map(([key, value]) => (
            <span key={key} className="text-[11px] text-ash/80">
              {key}: <span className="text-chalk/70">{String(value)}</span>
            </span>
          ))}
        </div>
      </div>
    </Card>
  )
}
