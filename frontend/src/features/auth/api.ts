import { apiClient } from '../../lib/api/client'
import type { AuthConfig, AuthTokens, User } from '../../lib/api/types'

/*
 * Auth HTTP calls. Kept in the auth feature because they belong to it, the way
 * the backend keeps identity in `apps.accounts` rather than in a shared module;
 * every other endpoint lives in `lib/api/endpoints.ts`.
 */

/**
 * `POST /auth/token/` — sign in.
 *
 * The credential is an **email and a password**, and nothing else. The display
 * name is printed on every ladder row and every scoreboard, so accepting it as
 * a login would hand out half the credential to anyone reading the rankings.
 *
 * The server answers a wrong password, an unknown address and a malformed one
 * *identically*, and hashes against a dummy even for an address it has never
 * seen so the refusal cannot be told apart by how fast it comes back. There is
 * therefore nothing here for the client to branch on: "which of the two was
 * wrong?" is a question the API deliberately refuses to answer, and a form that
 * guessed would rebuild the account-existence oracle the backend removed.
 */
export async function login(email: string, password: string): Promise<AuthTokens> {
  const res = await apiClient.post<AuthTokens>('/auth/token/', { email, password })
  return res.data
}

/**
 * `POST /auth/token/refresh/` — a new access token, from the refresh token in
 * the HttpOnly cookie the browser sends by itself. No body: there is nothing
 * left for JS to send.
 */
export async function refresh(): Promise<AuthTokens> {
  const res = await apiClient.post<AuthTokens>('/auth/token/refresh/')
  return res.data
}

/** `POST /auth/logout/` — blacklists the refresh token and unsets its cookie. */
export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout/')
}

/**
 * `POST /auth/registration/` — an email, a password and confirming it.
 *
 * Validated as a whole before anything is written, so a refusal never leaves a
 * `User` without its `Player`. The response is a signed-in session already, so
 * there is no second sign-in call to make.
 *
 * No display name here. The account arrives with a generated one flagged
 * `player_name_is_auto` — never derived from the address, not even its local
 * part, because that name is published on every scoreboard — and the caller
 * sends the player straight to `/welcome` to choose the real one.
 */
export async function register(email: string, password: string): Promise<AuthTokens> {
  const res = await apiClient.post<AuthTokens>('/auth/registration/', {
    email,
    password1: password,
    password2: password,
  })
  return res.data
}

/** `POST /auth/google/` — exchange a Google OAuth access token for knowdown
 *  JWTs. The backend uses the access-token flow, so this sends `access_token`,
 *  not a `code`. A deployment with no Google credentials answers 400
 *  `google_oauth_not_configured` — and says so in advance through
 *  {@link getAuthConfig}, which is what the button keys off. */
export async function googleLogin(accessToken: string): Promise<AuthTokens> {
  const res = await apiClient.post<AuthTokens>('/auth/google/', { access_token: accessToken })
  return res.data
}

/** `GET /auth/me/` — hydrate the current user (needs a valid access token). */
export async function getMe(): Promise<User> {
  const res = await apiClient.get<User>('/auth/me/')
  return res.data
}

/** `PATCH /auth/me/` — correct the caller's own email address.
 *
 *  It can be added or changed here, never cleared: an account with no address
 *  has no way back in after a forgotten password. */
export async function updateMe(patch: { email?: string }): Promise<User> {
  const res = await apiClient.patch<User>('/auth/me/', patch)
  return res.data
}

/**
 * `GET /auth/config/` — which sign-in methods this deployment has credentials
 * for.
 *
 * Asked *before* the sign-in screen can draw itself, and not as a nicety: a
 * tier without password auth leaves `token/`, `registration/` and the password
 * reset routes **unmounted**, so they answer 404. A form posting to a route
 * that does not exist fails with nothing useful to say, which is why the screen
 * asks first rather than trying and interpreting the wreckage.
 */
export async function getAuthConfig(): Promise<AuthConfig> {
  const res = await apiClient.get<AuthConfig>('/auth/config/')
  return res.data
}

/**
 * `POST /auth/password/reset/` — ask for a reset link.
 *
 * Always resolves, and always with the same generic message: the server answers
 * identically whether or not the address matches an account, so there is
 * nothing for the caller to branch on beyond "the request itself failed"
 * (network, or the 429 its own throttle scope raises).
 */
export async function requestPasswordReset(email: string): Promise<void> {
  await apiClient.post('/auth/password/reset/', { email })
}

/** `POST /auth/password/reset/confirm/` — spend a reset link. `uid`/`token`
 *  come from the query string of the emailed link; a bad or already-used pair
 *  is a 400 the caller reads as `ApiError.message`. */
export async function confirmPasswordReset(
  uid: string,
  token: string,
  password: string,
): Promise<void> {
  await apiClient.post('/auth/password/reset/confirm/', {
    uid,
    token,
    new_password1: password,
    new_password2: password,
  })
}
