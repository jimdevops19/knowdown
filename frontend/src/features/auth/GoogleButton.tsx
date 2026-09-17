import { useState } from 'react'
import { useAuth } from './useAuth'
import { useAuthConfig } from './useAuthConfig'
import { Button } from '../../components/Button'
import { normalizeApiError } from '../../lib/api/errors'
import { GOOGLE_CLIENT_ID } from '../../lib/config'

/*
 * "Continue with Google" using Google Identity Services (GIS), token-model flow:
 *   click → GIS returns a Google access_token → POST /auth/google/ → knowdown JWTs.
 *
 * One button covers both cases on purpose: the server auto-signs-up an unknown
 * Google account (SOCIALACCOUNT_AUTO_SIGNUP, plus apps.accounts.adapters that
 * provisions the Player), so a visitor never has to decide between "register"
 * and "log in" the way the email form on the same page does.
 *
 * Sign-in needs credentials on *both* sides — VITE_GOOGLE_CLIENT_ID here and
 * GOOGLE_OAUTH_CLIENT_ID/_SECRET on the server (reported by GET /auth/config/,
 * see useAuthConfig). Rather than hide the button when they're missing, it
 * renders disabled with the reason, so a deployment mid-setup shows the
 * option is on the roadmap and the working email/password path stays visible.
 */

// Load the GIS script once, on demand.
let gisPromise: Promise<void> | null = null
function loadGis(): Promise<void> {
  if (window.google?.accounts?.oauth2) return Promise.resolve()
  if (!gisPromise) {
    gisPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.defer = true
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('Could not load Google sign-in.'))
      document.head.appendChild(script)
    })
  }
  return gisPromise
}

// Wrap the callback-based GIS token request in a promise.
function requestGoogleAccessToken(clientId: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const client = window.google!.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: 'openid email profile',
      callback: (response) => {
        if (response.error) reject(new Error(response.error))
        else resolve(response.access_token)
      },
    })
    client.requestAccessToken()
  })
}

/* Inline Google "G" so this doesn't depend on an external image. */
function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.71-1.57 2.68-3.89 2.68-6.62z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.41 5.41 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.47.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"
      />
    </svg>
  )
}

export function GoogleButton({
  onSuccess,
  onError,
}: {
  onSuccess: () => void
  onError: (message: string) => void
}) {
  const { loginWithGoogle } = useAuth()
  const [loading, setLoading] = useState(false)
  // Ask the server once whether it has Google credentials (assumed yes while
  // the probe is in flight, so a configured deployment never flickers through
  // a disabled state).
  const { googleEnabled, passwordEnabled } = useAuthConfig()

  const configured = Boolean(GOOGLE_CLIENT_ID) && googleEnabled
  const reason = !GOOGLE_CLIENT_ID
    ? 'Google sign-in isn’t set up yet — set VITE_GOOGLE_CLIENT_ID to enable it.'
    : 'Google sign-in isn’t set up on the server yet.'

  async function handleClick() {
    setLoading(true)
    try {
      await loadGis()
      const token = await requestGoogleAccessToken(GOOGLE_CLIENT_ID as string)
      await loginWithGoogle(token)
      onSuccess()
    } catch (err) {
      onError(err instanceof Error && !('response' in err) ? err.message : normalizeApiError(err).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button
        type="button"
        variant="secondary"
        size="full"
        onClick={handleClick}
        disabled={loading || !configured}
        title={configured ? undefined : reason}
        aria-describedby={!configured ? 'google-unavailable' : undefined}
        className="!normal-case !font-sans !tracking-normal"
      >
        <GoogleMark />
        {loading ? 'Connecting…' : 'Continue with Google'}
      </Button>
      {!configured && (
        <p id="google-unavailable" className="text-center text-xs text-ash">
          {passwordEnabled
            ? 'Coming soon — use email and password for now.'
            : 'Google sign-in isn’t switched on here yet — nothing to do but wait, sorry.'}
        </p>
      )}
    </div>
  )
}
