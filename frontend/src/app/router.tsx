import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from './layouts/AppShell'
import { RouteError } from './RouteError'
import { RequireAuth } from '../features/auth/RequireAuth'
import { HomePage } from '../pages/HomePage'
import { PlayPage } from '../pages/PlayPage'
import { MatchPage } from '../pages/MatchPage'
import { MatchesPage } from '../pages/MatchesPage'
import { MatchDetailPage } from '../pages/MatchDetailPage'
import { RankingsPage } from '../pages/RankingsPage'
import { PlayerProfilePage } from '../pages/PlayerProfilePage'
import { MePage } from '../pages/MePage'
import { HowToPlayPage } from '../pages/HowToPlayPage'
import { LoginPage } from '../pages/LoginPage'
import { RegisterPage } from '../pages/RegisterPage'
import { ChooseNamePage } from '../pages/ChooseNamePage'
import { ForgotPasswordPage } from '../pages/ForgotPasswordPage'
import { ResetPasswordPage } from '../pages/ResetPasswordPage'
import { NotFoundPage } from '../pages/NotFoundPage'

/*
 * The route tree.
 *
 *  - The doorway screens render standalone, in their own AuthLayout: the
 *    shell's nav is a list of places a signed-out visitor mostly cannot go.
 *  - Everything else lives inside AppShell.
 *  - Protected pages sit under <RequireAuth>, which renders them only when
 *    authenticated and otherwise redirects to /login carrying `?next=` — so a
 *    link into a live match survives the detour through signing in.
 *
 * ── What is public, and why ─────────────────────────────────────────────────
 * The home page, the rankings, any player's profile and the rules are all open.
 * They are the answer to "what would I be signing up for", and they cannot sit
 * behind signing up. Playing is what needs an account, and the home page's
 * category cards route through the guard rather than hiding.
 *
 * `/play/:category` and `/match/:id` are guarded for a harder reason than
 * convention: both open a WebSocket that the server closes with 4401 for an
 * unauthenticated client. Letting an anonymous visitor reach either would trade
 * a redirect for a socket that opens and dies.
 */
export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage />, errorElement: <RouteError /> },
  { path: '/register', element: <RegisterPage />, errorElement: <RouteError /> },
  // The second half of signing up. Standalone like the two above — it is still
  // the doorway, even though the person is signed in by the time they reach it.
  { path: '/welcome', element: <ChooseNamePage />, errorElement: <RouteError /> },
  { path: '/forgot-password', element: <ForgotPasswordPage />, errorElement: <RouteError /> },
  { path: '/reset-password', element: <ResetPasswordPage />, errorElement: <RouteError /> },
  {
    path: '/',
    element: <AppShell />,
    // Catches anything thrown below it — including by AppShell itself — and
    // shows the 500 screen instead of a blank page.
    errorElement: <RouteError />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'rankings', element: <RankingsPage /> },
      { path: 'rankings/:category', element: <RankingsPage /> },
      // Public: a profile is what a scoreboard already shows both players
      // mid-match, made reachable on its own.
      { path: 'players/:displayName', element: <PlayerProfilePage /> },
      { path: 'how-to-play', element: <HowToPlayPage /> },
      {
        element: <RequireAuth />,
        children: [
          { path: 'play/:category', element: <PlayPage /> },
          { path: 'match/:id', element: <MatchPage /> },
          { path: 'matches', element: <MatchesPage /> },
          // Deliberately a different segment from the live match above.
          // `/match/:id` is the socket; `/matches/:id` is the box score. One
          // rejoins a game, the other reads a finished one, and collapsing them
          // into one route would mean guessing which the player wanted from a
          // status that may have changed since the link was made.
          { path: 'matches/:id', element: <MatchDetailPage /> },
          { path: 'me', element: <MePage /> },
        ],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
