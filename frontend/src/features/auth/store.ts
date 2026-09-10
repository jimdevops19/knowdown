import { create } from 'zustand'
import { ApiError } from '../../lib/api/errors'
import type { User } from '../../lib/api/types'
import {
  setAccessTokenGetter,
  setAuthReadyWaiter,
  setOnAuthCleared,
  setTokenRefresher,
} from '../../lib/api/client'
import * as authApi from './api'

/*
 * The session.
 *
 *  - `accessToken` is kept in memory only and never persisted.
 *  - The refresh token is not state here at all: it lives in an HttpOnly cookie
 *    the browser holds and sends itself, scoped to the auth routes that read
 *    it. JS — including this store — never sees its value. A week-long,
 *    self-rotating credential in `localStorage` is one XSS payload away from a
 *    silent, permanent account takeover; an HttpOnly cookie is unreadable to
 *    injected script by construction.
 *  - `status` drives every guard, and stays `'loading'` until bootstrap
 *    resolves, so a reload on a protected page waits rather than bouncing.
 */

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

interface AuthState {
  accessToken: string | null
  user: User | null
  status: AuthStatus
  setAccessToken: (access: string) => void
  setUser: (user: User) => void
  setStatus: (status: AuthStatus) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()((set) => ({
  accessToken: null,
  user: null,
  status: 'loading',
  setAccessToken: (access) => set({ accessToken: access }),
  setUser: (user) => set({ user, status: 'authenticated' }),
  setStatus: (status) => set({ status }),
  logout: () => set({ accessToken: null, user: null, status: 'unauthenticated' }),
}))

/* --- Single-flight refresh -------------------------------------------------
 * Concurrent 401s share one in-flight refresh, so a page opening six queries at
 * once doesn't fire six refreshes at an endpoint with rotation switched on —
 * which would spend five valid refresh tokens and blacklist the session.
 *
 * Two outcomes, deliberately distinct, because a deploy must not look like a
 * logout. A refresh the server *rejects* (401/403) resolves to null: that
 * session really is over. A backend we cannot *reach* — a network drop, or the
 * 502/504 a proxy answers with for the seconds a pod is being replaced — is
 * retried and then thrown. Callers read null as "log out" and a throw as "not
 * now": the refresh cookie is still in the browser and still valid, so the
 * session survives the blip. */
const REFRESH_RETRY_DELAYS_MS = [500, 1500, 4000, 8000]

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/** Reachability, not validity: no response at all, or a 5xx in front of it. */
export function isBackendUnreachable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false
  return error.code === 'network_error' || (error.status ?? 0) >= 500
}

async function attemptRefresh(): Promise<string | null> {
  for (let attempt = 0; ; attempt++) {
    try {
      const { access } = await authApi.refresh()
      useAuthStore.getState().setAccessToken(access)
      return access
    } catch (error) {
      if (!isBackendUnreachable(error)) return null
      if (attempt >= REFRESH_RETRY_DELAYS_MS.length) throw error
      await sleep(REFRESH_RETRY_DELAYS_MS[attempt])
    }
  }
}

let refreshPromise: Promise<string | null> | null = null

export function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = attemptRefresh().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

/* --- Is the session settled yet? -------------------------------------------
 * A reload starts with no access token in memory and no client-visible signal
 * of whether a refresh cookie exists, so every cold load has to ask the server
 * once to find out. Any request sent before that answer comes back goes out
 * anonymous, and on a scoped endpoint that is terminal: `/matches/{id}/`
 * answers 403, which `client.ts` does not replay and `queryClient.ts` will not
 * retry. The page would then show "not yours" to the person whose match it is,
 * until they reloaded — and auth arriving a moment later would change nothing,
 * because the query key never changed and so nothing refetched.
 *
 * So the client holds requests here until the first refresh attempt resolves.
 * It lives in the client rather than as `enabled: status !== 'loading'` on each
 * query, because the per-query version has to be remembered on every scoped
 * fetch on every page and fails *silently* when forgotten.
 *
 * A failed refresh resolves rather than throws: the caller is then genuinely
 * anonymous and should get the server's real answer. An unreachable backend is
 * swallowed the same way — the held request goes out and fails on its own,
 * which is what it would have done anyway; the session is untouched and
 * AuthProvider keeps trying to rehydrate it. */
function authReady(): Promise<void> {
  const { status, accessToken } = useAuthStore.getState()
  if (status !== 'loading' || accessToken) return Promise.resolve()
  return refreshAccessToken().then(
    () => undefined,
    () => undefined,
  )
}

/* --- Wire the store into the API client (fills the seams from client.ts) --- */
setAccessTokenGetter(() => useAuthStore.getState().accessToken)
setTokenRefresher(refreshAccessToken)
setOnAuthCleared(() => useAuthStore.getState().logout())
setAuthReadyWaiter(authReady)
