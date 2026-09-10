import { useAuthStore } from './store'
import * as authApi from './api'
import { setMyAvatar, setMyDisplayName } from '../../lib/api/endpoints'

/*
 * The hook components use for auth. Reads reactive state from the store and
 * exposes the actions; because it selects from a Zustand store, anything using
 * it re-renders when the user or the status changes.
 *
 * Split from AuthProvider so this file exports only hooks and that one only
 * components — a module exporting both defeats React Fast Refresh.
 */
export function useAuth() {
  const user = useAuthStore((s) => s.user)
  const status = useAuthStore((s) => s.status)

  /** The credential is an email and a password — nothing else signs anyone in. */
  async function login(email: string, password: string) {
    const { access } = await authApi.login(email, password)
    useAuthStore.getState().setAccessToken(access)
    const me = await authApi.getMe()
    useAuthStore.getState().setUser(me)
  }

  async function register(email: string, password: string) {
    const { access } = await authApi.register(email, password)
    useAuthStore.getState().setAccessToken(access)
    const me = await authApi.getMe()
    useAuthStore.getState().setUser(me)
  }

  async function loginWithGoogle(googleAccessToken: string) {
    const { access } = await authApi.googleLogin(googleAccessToken)
    useAuthStore.getState().setAccessToken(access)
    const me = await authApi.getMe()
    useAuthStore.getState().setUser(me)
  }

  /** Correct the caller's own email address. */
  async function updateEmail(email: string) {
    const updated = await authApi.updateMe({ email })
    useAuthStore.getState().setUser(updated)
    return updated
  }

  /**
   * Claim a display name.
   *
   * The write lands on the Player, but `player_name` and
   * `player_name_is_auto` ride on the user in the store — so re-hydrate from
   * `/auth/me/` rather than patching one field locally and letting the two
   * drift. That flag is what every "pick a name" prompt keys on, and a stale
   * copy of it means the prompt keeps asking after the answer was given.
   */
  async function updateDisplayName(displayName: string) {
    await setMyDisplayName(displayName)
    const me = await authApi.getMe()
    useAuthStore.getState().setUser(me)
    return me
  }

  /** Set or remove the avatar; `null` removes it. Re-hydrates for the same
   *  reason the rename does — the URL is mirrored onto the user. */
  async function updateAvatar(image: File | null) {
    await setMyAvatar(image)
    const me = await authApi.getMe()
    useAuthStore.getState().setUser(me)
    return me
  }

  /**
   * Clears the local session immediately — the UI should not wait on a network
   * round trip to sign somebody out — and blacklists the refresh cookie
   * server-side in the background. Best-effort, since the person is already
   * gone from the client's point of view either way.
   */
  function logout() {
    useAuthStore.getState().logout()
    void authApi.logout()
  }

  return {
    user,
    status,
    isAuthenticated: status === 'authenticated',
    /** The player id the live match screen matches socket events against. */
    playerId: user?.player_id ?? null,
    /** True while the display name is still the generated placeholder. */
    needsDisplayName: !!user && user.player_name_is_auto,
    login,
    register,
    loginWithGoogle,
    updateEmail,
    updateDisplayName,
    updateAvatar,
    logout,
  }
}
