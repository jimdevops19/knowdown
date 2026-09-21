import { Link } from 'react-router-dom'
import { Eye, EyeOff, Image as ImageIcon, Pencil, Timer } from 'lucide-react'
import { Card } from '../../components/Card'
import { LevelChip } from '../../components/LevelChip'
import { StatusBadge } from '../../components/StatusBadge'
import type { ReactNode } from 'react'
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
 *
 * ## The actions sit outside the link, not inside it
 *
 * The card itself is one big `Link` into the rehearsal, which is what a click
 * anywhere on it should do. Edit and retire are therefore rendered in a strip
 * *beneath* it rather than in a corner of it: a `<button>` nested inside an
 * `<a>` is invalid HTML, and the browsers that tolerate it disagree about
 * whether the click navigates as well as fires — which on this card would mean
 * retiring a question and being thrown into a rehearsal of it.
 */
export function QuestionCatalogCard({
  question,
  typeLabel,
  onEdit,
  onToggleActive,
  busy = false,
  lockedReason,
  filterQuery,
}: {
  question: TesterQuestionCard
  /** The human name of the answer shape, from `GET /tester/config/` — the
   *  backend's own `QuestionType` label rather than a second copy of the eight
   *  names maintained over here. */
  typeLabel: string
  /** Opens the editor on this question's authored YAML. */
  onEdit?: () => void
  /** Writes `is_active` into the resource file and reloads the catalog from it
   *  — never a bare column edit, which the next sync would undo. */
  onToggleActive?: () => void
  /** A write against this question is in flight. Both verbs go dead, because
   *  they edit the same block of the same file. */
  busy?: boolean
  /** Why this deployment will not accept a write, or undefined where it will.
   *  Set, both verbs are greyed and carry this sentence on hover instead of
   *  being removed: a maintainer on staging is looking for the button, and
   *  "it is not here" leaves them to guess why, while "not here, do it from
   *  local" is the entire answer. See `TesterConfig.editable`. */
  lockedReason?: string
  /** The catalog's current filtration, as a URL query string (no leading
   *  `?`). Carried onto the rehearsal link so that page can offer Previous/
   *  Next over the same set of questions this card was clicked out of. */
  filterQuery?: string
}) {
  const card = (
    <Card
      as={Link}
      to={`/tester/${question.type}/${question.id}${filterQuery ? `?${filterQuery}` : ''}`}
      interactive
      edge={question.is_active ? 'court' : undefined}
      className={`flex flex-col ${question.is_active ? '' : 'opacity-75'}`}
    >
      {/* --- What it is -------------------------------------------------- */}
      <div className="flex flex-wrap items-center gap-2 border-b border-chalk/8 px-4 py-3">
        <span className="font-display text-[10px] font-bold uppercase tracking-[0.12em] text-volt">
          {typeLabel}
        </span>
        <LevelChip level={question.level} showLabel />
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

  if (!onEdit && !onToggleActive) return card

  return (
    <div className="flex flex-col">
      {card}
      <div className="flex items-center justify-end gap-1 px-1 pt-1.5">
        {onEdit && (
          <ActionButton
            onClick={onEdit}
            disabled={busy}
            lockedReason={lockedReason}
            icon={<Pencil size={13} aria-hidden />}
          >
            Edit
          </ActionButton>
        )}
        {onToggleActive && (
          <ActionButton
            onClick={onToggleActive}
            disabled={busy}
            /* Retiring is a write to the same YAML block the editor opens, so
               it is locked by the same flag — it only looks like a toggle. */
            lockedReason={lockedReason}
            icon={
              question.is_active ? <EyeOff size={13} aria-hidden /> : <Eye size={13} aria-hidden />
            }
          >
            {question.is_active ? 'Retire' : 'Restore'}
          </ActionButton>
        )}
      </div>
    </div>
  )
}

/** A quiet text verb under a card. Deliberately not `Button`: these sit under
 *  fifty cards at once, and the app's button is a display-face, uppercase,
 *  lifting thing built to be the one action on a screen. */
function ActionButton({
  onClick,
  disabled,
  lockedReason,
  icon,
  children,
}: {
  onClick: () => void
  disabled?: boolean
  lockedReason?: string
  icon: ReactNode
  children: ReactNode
}) {
  const locked = Boolean(lockedReason)
  return (
    /* The hover text hangs on this wrapper rather than on the button, and the
       button is `aria-disabled` rather than `disabled`, for one reason: a truly
       disabled control receives no mouse events, so a `title` on it never opens
       — the tooltip would be missing in exactly the case it exists for. */
    <span title={lockedReason} className="inline-flex">
      <button
        type="button"
        onClick={locked ? undefined : onClick}
        disabled={disabled && !locked}
        aria-disabled={locked || undefined}
        className={`inline-flex items-center gap-1.5 rounded-tile px-2 py-1 text-[11px] font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 ${
          locked
            ? 'cursor-not-allowed text-ash/40'
            : 'text-ash hover:bg-chalk/6 hover:text-chalk'
        }`}
      >
        {icon}
        {children}
      </button>
    </span>
  )
}
