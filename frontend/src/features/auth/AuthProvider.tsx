import { useEffect, type ReactNode } from 'react'
import { useAuthStore, refreshAccessToken, isBackendUnreachable } from './store'
import * as authApi from './api'

/*
 * Rehydrates the session on load. The refresh token lives in an HttpOnly cookie
 * (see store.ts), invisible to JS, so there is no client-side signal to check
 * first — every cold load just tries a refresh:
 *
 *   refresh → GET /auth/me/ → authenticated
 *   refresh refused (no cookie, or an expired one) → unauthenticated
 *   backend unreachable → keep waiting and try again (below)
 *
 * `status` stays 'loading' until this resolves, so guards can wait rather than
 * redirecting somebody away from the page they reloaded.
 */

/* A backend that cannot be reached is not a session that has ended, so a cold
 * load during a deploy must not land on the sign-in screen. store.ts already
 * retries the refresh itself for ~14s; these are the outer, slower attempts on
 * top of that, for an outage that outlasts a rollout. `status` stays 'loading'
 * throughout — the app shows its loading state and rehydrates by itself the
 * moment the backend answers. After the last one we give up and show the
 * signed-out UI; the cookie is still in the browser, so a later reload picks
 * the session back up. */
const BOOTSTRAP_RETRY_DELAYS_MS = [2_000, 5_000, 10_000, 20_000]

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export function AuthProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      const { setUser, logout } = useAuthStore.getState()
      for (let attempt = 0; !cancelled; attempt++) {
        try {
          const access = await refreshAccessToken()
          if (!access) break // the server refused the refresh: there is no session
          const me = await authApi.getMe()
          if (!cancelled) setUser(me)
          return
        } catch (error) {
          if (!isBackendUnreachable(error)) break
          if (attempt >= BOOTSTRAP_RETRY_DELAYS_MS.length) break
          await sleep(BOOTSTRAP_RETRY_DELAYS_MS[attempt])
        }
      }
      if (!cancelled) logout()
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  return <>{children}</>
}
