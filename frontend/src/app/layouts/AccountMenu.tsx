import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { LogOut, Swords, User } from 'lucide-react'
import type { ReactNode } from 'react'

/*
 * The account dropdown behind the profile circle — Profile and Matches
 * history, the two destinations "My matches" used to spend its own tab bar
 * slot on, plus Sign out beneath a divider. One component so the desktop
 * header avatar and the phone tab bar's profile icon open the same menu
 * rather than two things that drift apart — Sign out included, which used to
 * live in its own header-only button and so had no way in on the phone bar.
 *
 * `placement` flips the panel above the trigger on the phone bar, which is
 * pinned to the bottom edge and has no room to open downward.
 */

const MENU_ITEMS = [
  { to: '/me', label: 'Profile', icon: User },
  { to: '/matches', label: 'Matches history', icon: Swords },
]

export function AccountMenu({
  trigger,
  triggerClassName,
  triggerLabel,
  placement = 'down',
  align = 'end',
  rootClassName = '',
  onSignOut,
}: {
  /** The circle/pill itself — icon or avatar. The menu owns the surrounding
   *  `<button>`, so this should just be the visual content. */
  trigger: ReactNode
  triggerClassName: string
  triggerLabel: string
  placement?: 'up' | 'down'
  align?: 'start' | 'end' | 'center'
  /** Extra classes on the positioning wrapper, e.g. `flex-1` so this item
   *  claims the same width as its siblings in a flex row of tabs. */
  rootClassName?: string
  /** Renders a divider and a Sign out row beneath the destinations, when
   *  given — omitted where the trigger has nothing to sign out of. */
  onSignOut?: () => void
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const alignClass =
    align === 'start' ? 'left-0' : align === 'center' ? 'left-1/2 -translate-x-1/2' : 'right-0'
  const placementClass = placement === 'up' ? 'bottom-full mb-2' : 'top-full mt-2'

  return (
    <div ref={rootRef} className={`relative flex ${rootClassName}`.trim()}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={triggerLabel}
        title={triggerLabel}
        className={`min-w-0 flex-1 ${triggerClassName}`}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="menu"
          className={`absolute z-50 w-48 overflow-hidden rounded-btn border border-chalk/10 bg-raised py-1 shadow-elevated ${placementClass} ${alignClass}`}
        >
          {MENU_ITEMS.map((item) => {
            const Icon = item.icon
            return (
              <Link
                key={item.to}
                to={item.to}
                role="menuitem"
                onClick={() => setOpen(false)}
                className="flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-ash transition-colors hover:bg-chalk/6 hover:text-chalk"
              >
                <Icon size={16} />
                {item.label}
              </Link>
            )
          })}
          {onSignOut && (
            <>
              <div role="separator" aria-hidden className="my-1 border-t border-chalk/10" />
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false)
                  onSignOut()
                }}
                className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-sm text-ash transition-colors hover:bg-chalk/6 hover:text-chalk"
              >
                <LogOut size={16} />
                Sign out
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
