/*
 * The auth seam — four slots the auth store fills at startup, and the readers
 * every transport pulls them through.
 *
 * It lives in a file of its own rather than beside the axios instance because
 * there are **two** transports that need a token, not one. REST puts it in an
 * `Authorization` header; the WebSocket cannot (a browser's `WebSocket`
 * constructor takes no headers) and puts it in `?token=` instead, which is the
 * contract `apps.matches.authentication.JWTAuthMiddleware` reads. Both need the
 * same three things — the current token, a way to refresh it, and a promise
 * that the session has settled — so those three live here and neither
 * transport imports the other.
 *
 * The indirection itself is the point: the store injects these, so nothing
 * under `lib/` imports `features/auth`. That keeps the dependency one-way and
 * avoids the store → client → store cycle, which is the shape that silently
 * yields `undefined` at module load.
 */

let accessTokenGetter: () => string | null = () => null
let tokenRefresher: () => Promise<string | null> = async () => null
let authClearedHandler: () => void = () => {}
let authReadyWaiter: () => Promise<void> = async () => {}

export function setAccessTokenGetter(getter: () => string | null) {
  accessTokenGetter = getter
}
/** Single-flight refresh. Resolves to a new token, or to null when the server
 *  says the session is over; REJECTS when it could not reach the server at all.
 *  Only the null is a logout. */
export function setTokenRefresher(refresher: () => Promise<string | null>) {
  tokenRefresher = refresher
}
export function setOnAuthCleared(handler: () => void) {
  authClearedHandler = handler
}
/** Resolves once the session is settled — see `waitForAuthReady`. */
export function setAuthReadyWaiter(waiter: () => Promise<void>) {
  authReadyWaiter = waiter
}

export function getAccessToken(): string | null {
  return accessTokenGetter()
}
export function refreshAccessToken(): Promise<string | null> {
  return tokenRefresher()
}
export function notifyAuthCleared(): void {
  authClearedHandler()
}
/**
 * Resolves once the session is settled.
 *
 * Only the access token is in memory — a reload starts with none and has to
 * refresh for one — so anything that authenticates has to wait for this or it
 * races rehydration and goes out anonymous. Over REST that is a 401 the client
 * can replay. Over the socket it is a 4401 close, which is *permanent*: there
 * is no reconnect from it, and the player is told to sign in while signed in.
 */
export function waitForAuthReady(): Promise<void> {
  return authReadyWaiter()
}
