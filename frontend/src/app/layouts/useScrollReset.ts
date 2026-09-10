import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/*
 * Client-side navigation doesn't touch the window's scroll position the way a
 * real page load does, so arriving on a new page mid-scroll leaves you looking
 * at its middle. Put every new page back at the top.
 *
 * Keyed on the pathname alone: a `?page=` or `?tab=` change is the same page
 * rearranging itself, and yanking the viewport up under the reader there would
 * be its own bug. A `#anchor` wins too — the point of that link was to land
 * somewhere specific.
 */
export function useScrollReset() {
  const { pathname, hash } = useLocation()
  useEffect(() => {
    if (hash) return
    window.scrollTo(0, 0)
  }, [pathname, hash])
}
