import { NavLink, useLocation } from 'react-router-dom'
import type { NavItem } from './navItems'

/*
 * The phone nav: a fixed bar of icon buttons along the bottom edge,
 * thumb-reachable, in place of the sidebar (which needs a viewport both wide
 * and tall — see the `desk` variant in index.css).
 *
 * It is the nav for a *rotated* phone too. There the viewport is wide but only
 * ~360px tall, so the bar turns itself sideways: one short row, each icon with
 * its label beside it rather than under it. Height is the scarce axis in
 * landscape; width is the plentiful one.
 *
 * Every tab spells its label out, not just the active one: an icon alone is a
 * guess, and the guess is worst for exactly the people who can least afford it.
 * Being *here* is carried by colour and the lit pill instead, which is what the
 * active state was really saying all along.
 *
 * There is no overflow sheet, because there is nothing to overflow — knowdown
 * has four top-level destinations at most, and they fit. If a fifth is ever
 * added, fold, don't shrink: five is the width at which a label starts
 * truncating on a small phone.
 */

/** NavLink's `end` semantics, evaluated by hand where a class needs the answer. */
function isCurrent(pathname: string, item: NavItem): boolean {
  if (item.exact || item.to === '/') return pathname === item.to
  return pathname === item.to || pathname.startsWith(`${item.to}/`)
}

const TAB_CLASS =
  'flex min-w-0 flex-1 flex-col items-center gap-1 rounded-btn px-0.5 py-1.5 transition-colors duration-200 short:flex-row short:justify-center short:gap-1.5'

function pillClass(active: boolean): string {
  return `flex h-9 w-9 shrink-0 items-center justify-center rounded-full border transition-all duration-200 short:h-8 short:w-8 ${
    active
      ? 'border-volt/40 bg-volt/15 text-volt motion-safe:shadow-glow-cyan'
      : 'border-transparent text-ash active:bg-white/10'
  }`
}

function labelClass(active: boolean): string {
  return `w-full truncate text-center font-display text-[10px] font-semibold uppercase tracking-tight transition-colors duration-200 short:w-auto short:text-[11px] ${
    active ? 'text-volt' : 'text-ash'
  }`
}

export function MobileTabBar({ items }: { items: NavItem[] }) {
  const { pathname } = useLocation()

  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-50 flex items-stretch border-t border-white/6 bg-panel/85 px-1 pt-0.5 backdrop-blur-xl desk:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {items.map((item) => {
        const Icon = item.icon
        const active = isCurrent(pathname, item)
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.exact || item.to === '/'}
            aria-label={item.label}
            className={TAB_CLASS}
          >
            <span className={pillClass(active)}>
              <Icon size={20} />
            </span>
            {/* aria-hidden: the link already names itself via aria-label, with
                the full name rather than the abbreviated one. */}
            <span aria-hidden className={labelClass(active)}>
              {item.tabLabel ?? item.label}
            </span>
          </NavLink>
        )
      })}
    </nav>
  )
}
