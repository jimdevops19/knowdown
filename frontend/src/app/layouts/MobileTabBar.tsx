import { NavLink, useLocation } from 'react-router-dom'
import { isNavItemActive, type NavItem } from './navItems'

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
 * Being *here* is carried by colour and the lit tile instead, which is what
 * the active state was really saying all along.
 *
 * The bar itself is opaque, not frosted. It sits over scrolling content on the
 * one screen where a mis-tap costs a question, and a translucent bar means the
 * contrast behind every icon depends on whatever happens to be passing under
 * it at that moment.
 *
 * Every tab is a link, with no exceptions: five controls that look alike have to
 * act alike, so each one navigates and none of them opens a menu. Account
 * actions that aren't destinations — Matches history, Sign out — live behind the
 * avatar in the header, which is on screen here too.
 *
 * There is no overflow sheet, because there is nothing to overflow — knowdown
 * has four top-level destinations at most, and they fit. If a fifth is ever
 * added, fold, don't shrink: five is the width at which a label starts
 * truncating on a small phone.
 */

/*
 * Each glyph (see `../../components/icons/navIcons.tsx`) is a free-standing
 * dimensional object now — its own gradient, its own drop shadow — not a flat
 * badge on a plate, so it has no `currentColor` outline to recolour for "you
 * are here" the way a lucide icon would. That state moves to the tile behind
 * it instead: the active tab gets a lit `raised` panel under the whole
 * icon+label stack, the same "you are here" surface `SidebarLink` already uses
 * for the desktop nav.
 */
const TAB_CLASS =
  'flex min-w-0 flex-1 flex-col items-center gap-1 rounded-btn px-0.5 py-1.5 transition-colors duration-200 short:flex-row short:justify-center short:gap-1.5'

function tabClass(active: boolean): string {
  return active ? `${TAB_CLASS} bg-raised` : TAB_CLASS
}

function labelClass(active: boolean): string {
  const base =
    'w-full truncate text-center font-display text-[10px] font-bold [font-stretch:var(--display-wide)] uppercase tracking-[0.04em] transition-colors duration-200 short:w-auto short:text-[11px]'
  return `${base} ${active ? 'text-court' : 'text-ash'}`
}

export function MobileTabBar({ items }: { items: NavItem[] }) {
  const { pathname } = useLocation()

  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-50 flex items-stretch border-t border-chalk/10 bg-void px-1 pt-0.5 desk:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {items.map((item) => {
        const Icon = item.icon
        const active = isNavItemActive(pathname, item)

        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.exact || item.to === '/'}
            aria-label={item.label}
            className={tabClass(active)}
          >
            <Icon size={30} className="shrink-0" />
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
