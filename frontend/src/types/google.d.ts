/*
 * Minimal typings for the Google Identity Services (GIS) token client we use.
 * The GIS script attaches `google` to `window` at runtime; this tells
 * TypeScript about the small slice we call.
 * Docs: https://developers.google.com/identity/oauth2/web/guides/use-token-model
 */
export {}

interface GoogleTokenResponse {
  access_token: string
  error?: string
}

interface GoogleTokenClient {
  requestAccessToken: () => void
}

interface GoogleOAuth2 {
  initTokenClient(config: {
    client_id: string
    scope: string
    callback: (response: GoogleTokenResponse) => void
  }): GoogleTokenClient
}

declare global {
  interface Window {
    google?: {
      accounts: {
        oauth2: GoogleOAuth2
      }
    }
  }
}
