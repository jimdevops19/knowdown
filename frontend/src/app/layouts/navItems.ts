import { BookOpen, Home, Medal, Play, User } from 'lucide-react'
import type { ComponentType } from 'react'

/*
 * The app's top-level destinations, in one place because two navs render them:
 * the sidebar (AppShell, on `desk`) and the phone tab bar (MobileTabBar).
 */

export interface NavItem {
  to: string
  label: string
  icon: ComponentType<{ size?: number; className?: string }>
  /** Shorter name for the phone tab bar, where a slot is ~a fifth of the screen
   *  and the full label would truncate. Falls back to `label`, which is what
   *  the sidebar and every accessible name always use. */
  tabLabel?: string
  /** Highlight only on an exact URL match, not on nested routes. */
  exact?: boolean
  /** Extra path prefixes that also count as "here", beyond `to` itself — e.g.
   *  Play stays lit while a match found through it is in progress. */
  matchPrefixes?: string[]
  /** A colour this item carries while idle, so it reads as "go here" at a
   *  glance — swapped for the app's own accent (cyan) once you're actually in
   *  it, the same "you are here" colour every other tab uses. */
  accent?: 'gold'
  /** Renders as an account dropdown (Profile / Matches history) instead of a
   *  plain link — see `AccountMenu`. */
  dropdown?: true
  /** Only shown once signed in — a guest sees neither the nav slot nor the
   *  page it points at with real content (see `RankingsPage`'s own guard for
   *  the case where the URL is reached directly). */
  authOnly?: true
}

// Public, like the category cards it mirrors: guests can see it, and tapping
// a category routes them through sign-in via `/play/:category`'s own guard.
const PLAY_ITEM: NavItem = {
  to: '/play',
  label: 'Play',
  icon: Play,
  accent: 'gold',
  matchPrefixes: ['/play', '/match'],
}

/*
 * Every destination other than Play, in order around it. Play itself is
 * inserted at the dead centre of the final list (see `navItemsFor`) rather
 * than living at a fixed index here, because the centre slot moves — 2nd of 3
 * for a guest, 3rd of 5 once Rankings and Profile are in the mix — and a fixed
 * position would only be right for one of those two counts.
 */
export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Home', icon: Home },
  { to: '/rankings', label: 'Rankings', icon: Medal, authOnly: true },
  // Public: the rules are the clearest answer there is to "what would I be
  // signing up for", so they cannot sit behind signing up.
  { to: '/how-to-play', label: 'How to play', tabLabel: 'Rules', icon: BookOpen },
]

/*
 * Destinations that only make sense — and only route — when signed in.
 *
 * Profile renders as a dropdown (see `AccountMenu`) rather than a plain link:
 * match history moved under it, so the tab bar keeps its five-slot budget
 * without giving "My matches" a slot of its own.
 */
export const AUTH_NAV_ITEMS: NavItem[] = [{ to: '/me', label: 'Profile', icon: User, dropdown: true }]

/** Every top-level destination, Play centred, for the signed-in state given. */
export function navItemsFor(isAuthenticated: boolean): NavItem[] {
  const rest = isAuthenticated
    ? [...NAV_ITEMS, ...AUTH_NAV_ITEMS]
    : NAV_ITEMS.filter((item) => !item.authOnly)
  const center = Math.floor(rest.length / 2)
  return [...rest.slice(0, center), PLAY_ITEM, ...rest.slice(center)]
}

/** Whether `item` should read as "you are here" for the given pathname —
 *  shared by the sidebar and the phone tab bar so the two navs agree. */
export function isNavItemActive(pathname: string, item: NavItem): boolean {
  const prefixes = item.matchPrefixes ?? [item.to]
  return prefixes.some((prefix) => {
    if (item.exact || prefix === '/') return pathname === prefix
    return pathname === prefix || pathname.startsWith(`${prefix}/`)
  })
}
