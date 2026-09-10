import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './useAuth'
import { Loading } from '../../components/states'

/*
 * Route guard, used as a parent route: its children only render when
 * authenticated. While the session is still bootstrapping we wait — a reload on
 * a protected page must not bounce the player to /login only to bounce them
 * back a moment later.
 */
export function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <Loading label="Checking your session…" />

  if (status !== 'authenticated') {
    // Remember where they were headed so sign-in can send them back. This is
    // the path that carries somebody who tapped a link into a live match:
    // they sign in and land on the match, not on the home page.
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  return <Outlet />
}
