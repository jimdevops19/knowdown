import axios, { isAxiosError, type AxiosResponse } from 'axios'
import { API_URL } from '../config'
import { normalizeApiError } from './errors'
import {
  getAccessToken,
  notifyAuthCleared,
  refreshAccessToken,
  waitForAuthReady,
} from './session'
import type { Pagination } from './types'

/*
 * The single axios instance every request goes through:
 *  - baseURL: `${VITE_API_URL}/api/v1` (empty in dev → relative, via the proxy)
 *  - request interceptor: waits for the session, then attaches the Bearer token
 *  - response interceptor: unwraps the `{ data }` envelope and stashes `meta`
 *  - error interceptor: normalizes failures to a typed ApiError, and replays
 *    one 401 behind a single-flight refresh
 */

export const apiClient = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  // The refresh token rides an HttpOnly cookie (see features/auth/store.ts)
  // rather than a request body field, so the browser has to be told to send it.
  // A no-op for the same-origin proxy — cookies go out on same-origin requests
  // regardless — but required the moment VITE_API_URL points elsewhere.
  withCredentials: true,
})

/* --- Auth seams ------------------------------------------------------------
 * The slots themselves live in `./session`, because the socket needs the same
 * token this file does and cannot get it from a header. Re-exported here so the
 * auth store still registers them in one place. */
export {
  setAccessTokenGetter,
  setAuthReadyWaiter,
  setOnAuthCleared,
  setTokenRefresher,
} from './session'

/**
 * The calls that *establish* a session. They must never wait on one, or the
 * bootstrap refresh would be queued behind itself and nothing would ever load.
 */
function isCredentialExchange(url: string | undefined): boolean {
  if (!url) return false
  return ['/auth/token', '/auth/registration', '/auth/google'].some((path) => url.includes(path))
}

apiClient.interceptors.request.use(async (config) => {
  // Hold every request until the session is settled. Only the access token is
  // in memory — a reload starts with none and has to refresh for one — so
  // without this a page's first fetch races rehydration and goes out anonymous.
  //
  // That is invisible on a public endpoint (the ladder, a profile) and
  // permanent on a scoped one: `/matches/` answers an anonymous caller 401 and
  // `/matches/{id}/` answers 403, and a 403 is terminal at both rescue points
  // below — only a 401 is replayed, and queryClient refuses to retry any 4xx.
  // Waiting once here fixes it for every endpoint, rather than asking each
  // query to remember to be `enabled`.
  if (!isCredentialExchange(config.url)) await waitForAuthReady()
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/* --- Envelope unwrap + error normalization -------------------------------- */

/** After unwrapping, list responses carry pagination on `response.meta`. */
export interface ApiMeta {
  pagination?: Pagination
}

// Teach TypeScript that every AxiosResponse may carry our `meta` (declaration
// merging), so `res.meta` is typed at every call site.
declare module 'axios' {
  export interface AxiosResponse {
    meta?: ApiMeta
  }
}

apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    const body = response.data
    // Success bodies are `{ data, meta? }`; replace response.data with the
    // payload so callers never see the envelope, and keep meta reachable.
    if (body && typeof body === 'object' && 'data' in body) {
      response.data = (body as { data: unknown }).data
      response.meta = (body as { meta?: ApiMeta }).meta
    }
    return response
  },
  async (error) => {
    // On a 401, try one silent token refresh and replay the request. Skip the
    // credential endpoints themselves so we never loop on sign-in/refresh.
    if (isAxiosError(error) && error.response?.status === 401) {
      const original = error.config as (typeof error.config & { _retry?: boolean }) | undefined
      if (original && !original._retry && !isCredentialExchange(original.url)) {
        original._retry = true
        try {
          const newToken = await refreshAccessToken()
          if (newToken) {
            original.headers = original.headers ?? {}
            original.headers.Authorization = `Bearer ${newToken}`
            return apiClient(original)
          }
        } catch {
          // The refresh never reached a server (offline, or a rollout swapping
          // pods). That says nothing about whether the session is still good —
          // the refresh cookie is untouched — so leave the user signed in and
          // let this one request fail. The query layer retries transient
          // errors, and the next refresh will succeed. Clearing auth here is
          // what would make every deploy look like a mass logout.
          return Promise.reject(normalizeApiError(error))
        }
        // A refresh the server refused: the session really is over.
        notifyAuthCleared()
      }
    }
    return Promise.reject(normalizeApiError(error))
  },
)
