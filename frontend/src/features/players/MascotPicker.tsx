import { useState, type ReactNode } from 'react'
import { Check } from 'lucide-react'
import { MARKS, Mascot, getMark } from '../../components/avatars'
import { Button } from '../../components/Button'
import { Modal } from '../../components/Modal'

/*
 * Pick a mascot.
 *
 * ── Why the grid lives behind a button ───────────────────────────────────────
 * Forty-one heads inline is a wall of animals in the middle of a settings page
 * that is otherwise two short forms. Picking a mascot is a thing a player does
 * once, so it gets a door rather than a permanent room: a button that says what
 * it opens, and a modal that is nothing but the choice.
 *
 * ── Why no filter ────────────────────────────────────────────────────────────
 * There used to be a row of ball filters above the grid. Forty-two tiles fit on
 * one screen at six across, which makes filtering forty-two things a control
 * that costs a tap to save no scrolling. The whole set at once is also the only
 * way to see that it *is* a set.
 *
 * Six across × seven down is exactly the forty-one marks plus the way out, with
 * no ragged final row — "None" takes the first cell, because wearing nothing is
 * a real choice with a real look (initials on a colour generated from the name)
 * and nobody should scroll past forty animals to find it.
 */
export function MascotPicker({
  value,
  onChange,
  disabled = false,
}: {
  /** The key currently worn, or `null` for none. */
  value: string | null
  /** Called with the new key, or `null` when "None" is picked. */
  onChange: (mascot: string | null) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const worn = value ? getMark(value) : null

  function pick(mascot: string | null) {
    onChange(mascot)
    // Closes on the tap: the choice is the whole content of the window, so
    // staying open would leave the player hunting for a close button to
    // confirm something already saved.
    setOpen(false)
  }

  return (
    <>
      <Button variant="secondary" size="sm" disabled={disabled} onClick={() => setOpen(true)}>
        {worn ? 'Change avatar' : 'Choose avatar'}
      </Button>

      <Modal
        open={open}
        title="Choose your avatar"
        description={worn ? `Currently ${worn.label}.` : 'Currently your initials.'}
        onClose={() => setOpen(false)}
      >
        <ul className="grid grid-cols-6 gap-2">
          <li>
            <Tile
              selected={value === null}
              label="No mascot — show my initials"
              onClick={() => pick(null)}
            >
              <span className="font-display text-[9px] font-bold uppercase tracking-[0.06em] text-ash">
                None
              </span>
            </Tile>
          </li>
          {MARKS.map((mark) => (
            <li key={mark.key}>
              <Tile
                selected={value === mark.key}
                label={mark.label}
                onClick={() => pick(mark.key)}
              >
                <Mascot mascotKey={mark.key} size={40} className="h-full w-full" />
              </Tile>
            </li>
          ))}
        </ul>
      </Modal>
    </>
  )
}

function Tile({
  selected,
  label,
  onClick,
  children,
}: {
  selected: boolean
  label: string
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={selected}
      onClick={onClick}
      className={`relative flex aspect-square w-full items-center justify-center overflow-hidden rounded-tile border-2 bg-panel p-0.5 transition-colors ${
        selected ? 'border-court bg-court/10' : 'border-chalk/10 hover:border-chalk/30'
      }`}
    >
      {children}
      {selected && (
        <span
          aria-hidden
          className="absolute right-0 top-0 flex h-3.5 w-3.5 items-center justify-center rounded-pill bg-court text-void"
        >
          <Check size={10} strokeWidth={3.5} />
        </span>
      )}
    </button>
  )
}
