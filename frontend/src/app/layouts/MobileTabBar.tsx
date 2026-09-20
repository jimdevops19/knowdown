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
 * Being *here* is carried by colour and the lit plate instead, which is what
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

const TAB_CLASS =
  'flex min-w-0 flex-1 flex-col items-center gap-1 rounded-btn px-0.5 py-1.5 transition-colors duration-200 short:flex-row short:justify-center short:gap-1.5'

/*
 * The icon plate behind each tab.
 *
 * Squared off, and "you are here" is a solid orange fill with dark ink rather
 * than a tinted, glowing circle. A row of softly lit coloured circles along the
 * bottom edge is the stock mobile tab bar; a row of cut plates with exactly one
 * lit is a control panel, which is what this app should feel bolted to. It is
 * also plainly more legible — a filled plate carries across a room, where a
 * 15%-tint behind a coloured glyph does not.
 *
 * The lit plate is the brand orange — the same colour as the primary button and
 * the search rings. There is no longer a separate "live" hue to reserve: the
 * app has one loud colour, and "the thing you are on" is one of the things it
 * is for.
 *
 * Play gets no special plate of its own. It used to sit in a gold-bordered,
 * gold-tinted key that made it a second, permanently-lit accent along the bottom
 * of every screen. Now it is an ordinary tab whose *triangle* happens to be
 * orange — the glyph is already an unmistakable "start", and it doesn't need a
 * frame around it to say so.
 */
function plateClass(active: boolean, accent?: NavItem['accent']): string {
  const base =
    'flex h-9 w-9 shrink-0 items-center justify-center rounded-[11px] border transition-all duration-200 short:h-8 short:w-8'
  if (active) return `${base} border-court bg-court text-void`
  return `${base} border-transparent active:bg-chalk/10 ${
    accent === 'court' ? 'text-court' : 'text-ash'
  }`
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
            className={TAB_CLASS}
          >
            <span className={plateClass(active, item.accent)}>
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
