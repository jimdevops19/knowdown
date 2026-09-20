import { useState, type ReactNode } from 'react'
import { Check } from 'lucide-react'
import { BALLS, MARKS, Mascot, ball, type BallKind } from '../../components/avatars'

/*
 * Pick a mascot.
 *
 * ── Why a filter at all ──────────────────────────────────────────────────────
 * Forty-one heads in one grid is a wall. The ball each one holds is the only
 * attribute of a mascot that is true at *scoreboard* size — at 24px the animal
 * is a silhouette and the ball is three pixels of colour — so it is the thing
 * worth filtering by, and the filter doubles as an explanation of why the
 * liveries exist. The founding sixteen hold nothing, which is its own filter.
 *
 * ── Why "None" is first and not last ─────────────────────────────────────────
 * Wearing nothing is a real choice with a real look (initials on a colour
 * generated from the name), not the absence of one, and a player who wants
 * their initials back should not have to scroll past forty animals to find the
 * way out.
 *
 * The grid is `auto-fill` at a 56px minimum: five across on the narrowest phone
 * this app supports, and it fills out on a laptop without ever becoming a row
 * of tiny targets. Every tile is its own 56px touch target, which is the number
 * the answer tiles use.
 */
type Filter = 'all' | 'none' | BallKind

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'none', label: 'No ball' },
  ...(Object.keys(BALLS) as BallKind[]).map((kind) => ({
    value: kind as Filter,
    label: BALLS[kind].name,
  })),
]

export function MascotPicker({
  value,
  onChange,
  disabled = false,
}: {
  /** The key currently worn, or `null` for none. */
  value: string | null
  /** Called with the new key, or `null` when "None" is pressed. */
  onChange: (mascot: string | null) => void
  disabled?: boolean
}) {
  const [filter, setFilter] = useState<Filter>('all')

  const shown = MARKS.filter((mark) => {
    if (filter === 'all') return true
    if (filter === 'none') return mark.ball === null
    return mark.ball === filter
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by ball">
        {FILTERS.map(({ value: option, label }) => {
          const on = filter === option
          return (
            <button
              key={option}
              type="button"
              aria-pressed={on}
              onClick={() => setFilter(option)}
              className={`inline-flex items-center gap-1.5 rounded-pill border px-3 py-1.5 font-display text-[11px] font-bold [font-stretch:var(--display-wide)] uppercase tracking-[0.1em] transition-colors ${
                on
                  ? 'border-court bg-court/15 text-court'
                  : 'border-chalk/12 text-ash hover:border-chalk/25 hover:text-chalk'
              }`}
            >
              {/* The swatch is the real ball, drawn at size — a flat disc would
                  make "Red, white and blue" and "White" the same picture. */}
              {option !== 'all' && option !== 'none' && (
                <svg
                  viewBox="0 0 64 64"
                  width={14}
                  height={14}
                  aria-hidden
                  dangerouslySetInnerHTML={{ __html: ball(option as BallKind, 32, 32, 30) }}
                />
              )}
              {label}
            </button>
          )
        })}
      </div>

      <ul className="grid grid-cols-[repeat(auto-fill,minmax(56px,1fr))] gap-2">
        <li>
          <Tile
            selected={value === null}
            label="No mascot — show my initials"
            disabled={disabled}
            onClick={() => onChange(null)}
          >
            <span className="font-display text-[10px] font-bold uppercase tracking-[0.08em] text-ash">
              None
            </span>
          </Tile>
        </li>
        {shown.map((mark) => (
          <li key={mark.key}>
            <Tile
              selected={value === mark.key}
              label={mark.label}
              disabled={disabled}
              onClick={() => onChange(mark.key)}
            >
              <Mascot mascotKey={mark.key} size={44} />
            </Tile>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Tile({
  selected,
  label,
  disabled,
  onClick,
  children,
}: {
  selected: boolean
  label: string
  disabled: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
      className={`relative flex aspect-square w-full items-center justify-center rounded-tile border-2 bg-panel transition-colors disabled:opacity-50 ${
        selected
          ? 'border-court bg-court/10'
          : 'border-chalk/10 hover:border-chalk/30'
      }`}
    >
      {children}
      {selected && (
        <span
          aria-hidden
          className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-pill bg-court text-void"
        >
          <Check size={11} strokeWidth={3.5} />
        </span>
      )}
    </button>
  )
}
