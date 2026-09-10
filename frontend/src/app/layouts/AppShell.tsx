import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { LogOut, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { Logo, LogoMark } from '../../components/Logo'
import { Avatar } from '../../components/Avatar'
import { Button } from '../../components/Button'
import { useAuth } from '../../features/auth/useAuth'
import { MobileTabBar } from './MobileTabBar'
import { navItemsFor, type NavItem } from './navItems'
import { useScrollReset } from './useScrollReset'

/*
 * The persistent chrome around every page: a glass sidebar of nav links plus a
 * glass header, floating over the app's layered background (index.css). The
 * current page renders where <Outlet /> sits — this layout stays mounted and
 * only the outlet swaps as you navigate.
 *
 * Responsive: the sidebar shows on `desk` viewports — wide *and* tall enough
 * for it. Everywhere else, including a phone turned on its side (~800x360 CSS
 * px, which is wide but very short), it gives way to a fixed bar of icons along
 * the bottom edge. See the `phone`/`desk`/`short` variants in index.css.
 *
 * The sidebar can also be dismissed outright with the header toggle, and the
 * choice sticks across reloads — closing the nav is a working posture, not a
 * per-page whim. The phone bar has no such toggle: it is the only nav there,
 * and it costs one row.
 */

const NAV_OPEN_KEY = 'knowdown:nav-open'

function useNavOpen(): [boolean, () => void] {
  const [open, setOpen] = useState(() => localStorage.getItem(NAV_OPEN_KEY) !== 'false')
  useEffect(() => {
    localStorage.setItem(NAV_OPEN_KEY, String(open))
  }, [open])
  return [open, () => setOpen((prev) => !prev)]
}

function SidebarLink({ item }: { item: NavItem }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      // `end` makes the link match only its exact path, not every nested route
      // ("/" would otherwise match everything).
      end={item.exact || item.to === '/'}
      className={({ isActive }) =>
        [
          'group relative flex items-center gap-3 rounded-btn px-3 py-2.5 text-sm font-medium transition-all duration-200',
          isActive
            ? 'bg-court/90 text-chalk motion-safe:shadow-glow-violet'
            : 'text-ash hover:bg-white/6 hover:text-chalk',
        ].join(' ')
      }
    >
      {({ isActive }) => (
        <>
          {/* Left accent bar on the active item. */}
          <span
            aria-hidden
            className={`absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-volt transition-opacity duration-200 ${
              isActive ? 'opacity-100' : 'opacity-0'
            }`}
          />
          <Icon size={18} />
          {item.label}
        </>
      )}
    </NavLink>
  )
}

/*
 * The one control that opens and closes the nav, in the header either way.
 * Deliberately the same 36px glass icon button as the account control beside
 * it, so the header reads as one row rather than a hamburger bolted on. State
 * is carried by the icon's arrow and by a cyan tint while the nav is stowed —
 * the same accent the sidebar uses for "you are here", saying something is
 * parked out of view.
 */
function NavToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const Icon = open ? PanelLeftClose : PanelLeftOpen
  const label = open ? 'Hide navigation' : 'Show navigation'
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls="app-nav"
      aria-label={label}
      title={label}
      // Hidden wherever there is no sidebar: what it opens is the sidebar, and
      // on a phone the nav is the bottom bar, which stays put.
      className={`hidden h-9 w-9 shrink-0 items-center justify-center rounded-btn transition-colors hover:bg-raised hover:text-chalk desk:flex ${
        open ? 'text-ash' : 'bg-white/6 text-volt'
      }`}
    >
      <Icon size={18} />
    </button>
  )
}

/** The account control: the avatar and a way out when signed in, the way in
 *  when not. Not a dropdown — there are two actions total, and a menu holding
 *  two items is a tap somebody has to make to find out there was nothing in it. */
function AccountControl() {
  const { isAuthenticated, user, logout } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    const next = encodeURIComponent(location.pathname + location.search)
    return (
      <Button as={Link} to={`/login?next=${next}`} size="sm" variant="secondary">
        Sign in
      </Button>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <Link
        to="/me"
        className="flex items-center gap-2 rounded-btn px-1 py-1 transition-colors hover:bg-white/6"
        title="Your profile"
      >
        <Avatar
          name={user?.player_name ?? '?'}
          seed={user?.player_id ?? undefined}
          avatarUrl={user?.player_avatar_url ?? null}
          size={30}
        />
        <span className="hidden max-w-32 truncate text-sm text-ash sm:inline">
          {user?.player_name}
        </span>
      </Link>
      <button
        type="button"
        onClick={logout}
        aria-label="Sign out"
        title="Sign out"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-btn text-ash transition-colors hover:bg-raised hover:text-chalk"
      >
        <LogOut size={17} />
      </button>
    </div>
  )
}

export function AppShell() {
  useScrollReset()
  const { isAuthenticated } = useAuth()
  const [navOpen, toggleNav] = useNavOpen()
  const navItems = navItemsFor(isAuthenticated)

  return (
    <div className="relative flex min-h-full">
      {/* Sidebar — glass, floating over the body's layered background. Closing
          it animates the width to zero; the inner column keeps its own width so
          the links slide out of view instead of reflowing on the way. `inert`
          keeps the hidden links out of tab order and screen readers. */}
      <aside
        id="app-nav"
        inert={!navOpen}
        className={`sticky top-0 hidden h-screen shrink-0 flex-col overflow-hidden bg-panel/60 backdrop-blur-xl transition-[width] duration-300 desk:flex ${
          navOpen ? 'w-60 border-r border-white/6' : 'w-0'
        }`}
      >
        {/* Top padding is spelled out rather than using `pt-safe`: that utility
            has no floor, and as a longhand it would override `p-4` and pin the
            brand to y=0 — sitting visibly higher than the header row beside it
            across the divider. */}
        <div className="flex w-60 shrink-0 flex-col gap-6 p-4 pt-[max(1rem,env(safe-area-inset-top))]">
          <Link to="/" aria-label="knowdown — home">
            <Logo />
          </Link>
          <nav className="flex flex-col gap-1">
            {navItems.map((item) => (
              <SidebarLink key={item.to} item={item} />
            ))}
          </nav>
        </div>
      </aside>

      {/* Main column: header + routed content */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Horizontal padding tracks <main> below, so the header's controls sit
            on the same margins as the page content rather than hugging the
            window edge. On a short viewport the header gives a row back to the
            page: 64px of chrome out of 360px of height is a sixth of the
            screen, and the row only carries a brand and two controls. */}
        <header className="pt-safe px-safe sticky top-0 z-30 flex h-[calc(4rem+env(safe-area-inset-top))] items-center justify-between gap-4 border-b border-white/6 bg-panel/50 backdrop-blur-xl sm:[--pad-x:1.5rem] lg:[--pad-x:2rem] short:h-[calc(3rem+env(safe-area-inset-top))]">
          <div className="flex min-w-0 items-center gap-2">
            <NavToggle open={navOpen} onToggle={toggleNav} />
            {/* The brand lives in the header wherever the sidebar isn't showing
                it: on phone chrome always, on desk once the sidebar is closed.
                Just the mark on a phone — the wordmark plus an account control
                is more than a 360px row can carry. */}
            <Link to="/" aria-label="knowdown — home" className={navOpen ? 'desk:hidden' : ''}>
              <span className="desk:hidden">
                <LogoMark size={30} />
              </span>
              <span className="hidden desk:block">
                <Logo />
              </span>
            </Link>
          </div>
          <AccountControl />
        </header>

        {/* Gutters ride on `--pad-x`/`--pad-b` so `px-safe`/`pb-safe` keep their
            notch clearance at every breakpoint (see index.css). */}
        <main className="pb-safe px-safe mx-auto w-full max-w-5xl flex-1 pt-4 sm:pt-6 sm:[--pad-b:1.5rem] sm:[--pad-x:1.5rem] lg:pt-8 lg:[--pad-b:2rem] lg:[--pad-x:2rem] short:pt-3">
          <Outlet />
        </main>

        {/* Clearance for the fixed bottom bar, so the last row of a page is
            never parked under it. A spacer rather than padding on <main>: the
            padding there is already set at three breakpoints. */}
        <div aria-hidden className="desk:hidden" style={{ height: 'var(--nav-bar-inset)' }} />
      </div>

      <MobileTabBar items={navItems} />
    </div>
  )
}
