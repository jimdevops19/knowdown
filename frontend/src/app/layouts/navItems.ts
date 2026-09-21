import type { ComponentType } from 'react'
import { HomeIcon, PlayIcon, RankingsIcon, RulesIcon } from '../../components/icons/navIcons'

/*
 * The app's top-level destinations, in one place because two navs render them:
 * the sidebar (AppShell, on `desk`) and the phone tab bar (MobileTabBar).
 */

export interface NavItem {
  to: string
  label: string
  icon: ComponentType<{ size?: number; className?: string }>
  /** Shorter name for the phone tab bar, where a slot is ~a quarter of the
   *  screen and the full label would truncate. Falls back to `label`, which is
   *  what the sidebar and every accessible name always use. */
  tabLabel?: string
  /** Highlight only on an exact URL match, not on nested routes. */
  exact?: boolean
  /** Extra path prefixes that also count as "here", beyond `to` itself — e.g.
   *  Play stays lit while a match found through it is in progress. */
  matchPrefixes?: string[]
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
  icon: PlayIcon,
  matchPrefixes: ['/play', '/match'],
}

/*
 * Every destination other than Play, in order around it. Play itself is
 * inserted at the dead centre of the final list (see `navItemsFor`) rather
 * than living at a fixed index here, because the centre slot moves — 2nd of 3
 * for a guest, 3rd of 4 once Rankings joins them signed in — and a fixed
 * position would only be right for one of those two counts.
 */
export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Home', icon: HomeIcon },
  // `Ranks` in the bar: even at four tabs on a 320px phone "Rankings" is the
  // one label that runs past the slot, so the tab showed "Rankin…". The
  // accessible name stays the full word.
  { to: '/rankings', label: 'Rankings', tabLabel: 'Ranks', icon: RankingsIcon, authOnly: true },
  // Public: the rules are the clearest answer there is to "what would I be
  // signing up for", so they cannot sit behind signing up.
  { to: '/how-to-play', label: 'How to play', tabLabel: 'Rules', icon: RulesIcon },
]

/*
 * Profile has no slot of its own here: it would be the fifth tab and a
 * duplicate of the account menu that already hangs off the avatar in the
 * header, on screen at every width. That menu (Profile, Matches history, Sign
 * out) is the one place account destinations live — the dock stays four.
 */

/** Every top-level destination, Play centred, for the signed-in state given. */
export function navItemsFor(isAuthenticated: boolean): NavItem[] {
  const rest = isAuthenticated ? NAV_ITEMS : NAV_ITEMS.filter((item) => !item.authOnly)
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
