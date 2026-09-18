/// <reference lib="webworker" />
/*
 * knowdown's service worker.
 *
 * This is a *hand-written* worker (strategies: 'injectManifest' in
 * vite.config.ts) rather than the one vite-plugin-pwa would generate, and the
 * caching below is a faithful port of what `generateSW` produces from those
 * same options. If you change one, change the other — the reasons are
 * load-bearing:
 *
 *  - The worker serves *static build output only*. Live data (/api, /ws) is
 *    excluded from the navigation fallback and never cached; a stale match, a
 *    stale ladder or a stale question is worse than none at all.
 *  - `skipWaiting` is **not** automatic. A player ten seconds into a question
 *    must not have the page swapped under them, so a new build waits for a tap
 *    on Reload (see features/pwa/PwaPrompts.tsx), which is what sends the
 *    SKIP_WAITING message handled below.
 *
 * Authoring it also leaves somewhere to put a `push` handler the day the
 * backend grows one — a generated worker cannot host custom events, and a push
 * that arrives with nothing listening does nothing at all.
 */
import { clientsClaim } from 'workbox-core'
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'

declare const self: ServiceWorkerGlobalScope

// ── Precache ────────────────────────────────────────────────────────────────
// __WB_MANIFEST is replaced at build time with the file list produced by the
// `injectManifest` globs in vite.config.ts.
precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

// SPA history fallback, mirroring nginx's `try_files ... /index.html`. The
// denylist keeps the API, the websockets and Django's own surfaces off the
// worker's shell.
registerRoute(
  new NavigationRoute(createHandlerBoundToURL('/index.html'), {
    denylist: [/^\/api\//, /^\/ws\//, /^\/admin\//, /^\/static\//, /^\/media\//],
  }),
)

clientsClaim()

// The waiting worker takes over only when the page asks it to. `useRegisterSW`
// (virtual:pwa-register/react) posts this when the player taps Reload.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') void self.skipWaiting()
})
