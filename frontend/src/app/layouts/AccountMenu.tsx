import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { LogOut, Swords, User, Wrench } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTesterAccess } from '../../features/tester/useTesterAccess'

/*
 * The account dropdown behind the avatar in the header — Profile and Matches
 * history, the two destinations "My matches" used to spend its own tab bar slot
 * on, plus Sign out beneath a divider.
 *
 * The avatar is the only thing that opens it, at every width. The phone tab
 * bar's Profile tab used to open it too, which meant the one control in that
 * row that looked like a link wasn't one: tapping it popped a sheet instead of
 * going to the profile page, and a tab that behaves differently from the four
 * beside it is a bug however it's spelled. That tab is now a plain link, and
 * the menu lives where a menu is expected — behind the face, not behind a tab.
 *
 * The question tester hangs here too, for the handful of accounts that have one
 * (`useTesterAccess` asks the server; almost every caller is told no). It is
 * deliberately *not* in `navItems.ts` beside Home, Play and Rankings: those are
 * the product, this is a workbench, and the phone tab bar has a five-slot
 * budget that a maintainer tool has no business spending. A menu is also where
 * an entry that exists for some people and not others belongs — a nav with a
 * hole in it reads as a bug, a menu with one more row does not.
 */

const MENU_ITEMS = [
  { to: '/me', label: 'Profile', icon: User },
  { to: '/matches', label: 'Matches history', icon: Swords },
]

export function AccountMenu({
  trigger,
  triggerClassName,
  triggerLabel,
  align = 'end',
  onSignOut,
}: {
  /** The circle/pill itself — icon or avatar. The menu owns the surrounding
   *  `<button>`, so this should just be the visual content. */
  trigger: ReactNode
  triggerClassName: string
  triggerLabel: string
  align?: 'start' | 'end' | 'center'
  /** Renders a divider and a Sign out row beneath the destinations, when
   *  given — omitted where the trigger has nothing to sign out of. */
  onSignOut?: () => void
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const tester = useTesterAccess()

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

  return (
    <div ref={rootRef} className="relative flex">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={triggerLabel}
        title={triggerLabel}
        className={`min-w-0 ${triggerClassName}`}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="menu"
          className={`absolute top-full z-50 mt-2 w-48 overflow-hidden rounded-btn border border-chalk/10 bg-raised py-1 shadow-elevated ${alignClass}`}
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
          {tester.available && (
            <Link
              to="/tester"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-ash transition-colors hover:bg-chalk/6 hover:text-chalk"
            >
              <Wrench size={16} />
              Question tester
            </Link>
          )}
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
