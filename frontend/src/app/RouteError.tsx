import { isRouteErrorResponse, useRouteError } from 'react-router-dom'
import { NotFoundPage } from '../pages/NotFoundPage'
import { ServerErrorPage } from '../pages/ServerErrorPage'

/*
 * The router's last line of defence (`errorElement` in router.tsx).
 *
 * Anything a route throws on its way to the screen ends up here — a component
 * that blew up while rendering, a lazy chunk that failed to load after a deploy
 * replaced it, a router-level 404. Without it React Router unmounts the tree
 * and leaves a blank page, which is the one failure mode a player mid-match can
 * do nothing about.
 *
 * It renders *outside* AppShell — the error replaces the layout it happened
 * inside — so it brings its own full-height frame: the shell it would normally
 * sit next to may be exactly what failed.
 */
export function RouteError() {
  const error = useRouteError()

  // Surfaced in the console as well: the screen tells the visitor what to do,
  // this tells whoever is looking at the tab what actually happened.
  console.error('Route error:', error)

  const isNotFound = isRouteErrorResponse(error) && error.status === 404

  return (
    <div className="px-safe flex min-h-dvh items-center justify-center py-10">
      {isNotFound ? <NotFoundPage /> : <ServerErrorPage />}
    </div>
  )
}
