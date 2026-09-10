import { BookOpen, Home, Medal, Swords, User } from 'lucide-react'
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
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Home', icon: Home },
  { to: '/rankings', label: 'Rankings', icon: Medal },
  // Public: the rules are the clearest answer there is to "what would I be
  // signing up for", so they cannot sit behind signing up.
  { to: '/how-to-play', label: 'How to play', tabLabel: 'Rules', icon: BookOpen },
]

/*
 * Destinations that only make sense — and only route — when signed in.
 *
 * "My matches" is exact: `/matches/:id` shows one specific match reachable from
 * several places, and a detail page must not light up this tab as though the
 * player were browsing their history.
 */
export const AUTH_NAV_ITEMS: NavItem[] = [
  { to: '/matches', label: 'My matches', tabLabel: 'Matches', icon: Swords, exact: true },
  { to: '/me', label: 'Profile', icon: User },
]

/** Every top-level destination, in sidebar order, for the signed-in state given. */
export function navItemsFor(isAuthenticated: boolean): NavItem[] {
  return isAuthenticated ? [...NAV_ITEMS, ...AUTH_NAV_ITEMS] : NAV_ITEMS
}
