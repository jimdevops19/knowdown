import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load .env* so VITE_PROXY_TARGET set there reaches the dev proxy below. A
  // real process env var of the same name still wins (loadEnv merges it in).
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000'

  return {
    // Tailwind v4 plugs straight into Vite — no separate config file and no
    // PostCSS setup; the whole theme lives in CSS (see src/index.css).
    plugins: [
      react(),
      tailwindcss(),
      // ── PWA ─────────────────────────────────────────────────────────────
      // What turns the build into an installable app: a web manifest, so a
      // phone can add knowdown to its home screen and run it without browser
      // chrome, plus a Workbox service worker that precaches the built shell.
      //
      // The worker only ever serves *static build output*. Everything this app
      // shows — a live match, the ladder, the question board — is behind /api
      // and /ws, and a cached scoreboard is worse than no scoreboard, so those
      // paths are kept off the worker entirely (see the denylist in src/sw.ts)
      // and always go to the network.
      VitePWA({
        // 'prompt', not 'autoUpdate': a player six seconds into a question must
        // not have the page swapped under them. A new build raises the reload
        // banner (PwaPrompts) and waits for a tap.
        registerType: 'prompt',
        injectRegister: null, // registration lives in features/pwa/PwaPrompts.tsx
        // We author the worker (src/sw.ts) rather than have one generated: a
        // generated worker can only precache, and the moment this app wants a
        // `push` handler ("your opponent is ready") there is nowhere to put it.
        // src/sw.ts re-implements the precaching a generated worker would do —
        // the two must be kept in step.
        strategies: 'injectManifest',
        srcDir: 'src',
        filename: 'sw.ts',
        manifest: {
          id: '/',
          name: 'knowdown — real-time 1v1 trivia',
          short_name: 'knowdown',
          description:
            'Get paired with a stranger and race them through seven NBA questions on one clock.',
          start_url: '/',
          scope: '/',
          display: 'standalone',
          // Locked to portrait: the board is a column of answer tiles sized to
          // a thumb, and a rotated phone is the one viewport where the clock
          // and the tiles stop fitting together (see the `short` variant in
          // index.css for how hard the landscape case already has to be fought).
          orientation: 'portrait',
          // The app chrome (index.css --color-court-black / --color-void), so
          // the OS status bar and the splash screen are the app's own dark
          // rather than a white flash before the first paint.
          theme_color: '#101210',
          background_color: '#0b0b0b',
          categories: ['games', 'sports', 'trivia'],
          icons: [
            { src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
            { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
            // Maskable icons keep the mark inside the 80% safe zone, so Android
            // can crop the tile to whatever shape the launcher uses.
            { src: '/icon-maskable-192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
            { src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          ],
          // Long-press the home screen icon → straight into a section.
          shortcuts: [
            { name: 'Play', url: '/play' },
            { name: 'Rankings', url: '/rankings' },
            { name: 'How to play', url: '/how-to-play' },
          ],
        },
        // Under `injectManifest` this block decides only *what goes into the
        // precache manifest*. The behavioural half — the navigation fallback and
        // its denylist, clientsClaim, skipWaiting, cleanupOutdatedCaches — is
        // code at the top of src/sw.ts, because an authored worker is the thing
        // doing that work. Change it there.
        injectManifest: {
          // The fonts are self-hosted (@fontsource), so the woff2 belong in the
          // precache too — without them the first offline paint drops to
          // system-ui, which is most of the brand gone.
          globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
          // Weight the install: @fontsource ships every subset of both faces,
          // and an English-only UI never touches the non-latin ones. They still
          // load fine from the network — they are simply not front-loaded onto
          // every phone that opens the app. (The home-screen icons *are*
          // precached, by `includeManifestIcons`, which defaults to true; at
          // ~70 KB for the set that is a fair trade for an install that works
          // on a bad connection.)
          globIgnores: ['**/*cyrillic*', '**/*greek*', '**/*vietnamese*'],
        },
        // The SW is off in `vite dev` — HMR and a precaching worker disagree
        // loudly. Flip `enabled` to exercise the install/update flow locally.
        devOptions: { enabled: false, type: 'module' },
      }),
    ],
    server: {
      port: 5173,
      // Bind all interfaces (not just localhost) so a phone on the same
      // wifi can reach this dev server at the machine's LAN IP.
      host: true,
      proxy: {
        // The browser calls same-origin "/api/..." on :5173 and Vite forwards
        // it to Django. Same-origin from the browser's point of view, so there
        // is no CORS to configure and the API client's baseURL stays relative.
        //
        // `/ws` first: an object of proxy rules is matched in insertion order,
        // and it needs `ws: true` so the connection is upgraded rather than
        // buffered. In the cluster the same split is nginx's job — /ws/ to the
        // `realtime` (uvicorn/ASGI) deployment, /api/ to `api` (gunicorn/WSGI).
        // Two deployments of one image; see backend/config/asgi.py.
        '/ws': { target, ws: true, changeOrigin: true },
        '/api': { target, changeOrigin: true },
        // Question images and player avatars. The backend emits root-relative
        // URLs precisely so this same-origin proxy is what resolves them — an
        // absolute one would bake in whichever host was on the Django request,
        // which breaks the moment the app is opened from another device.
        '/media': { target, changeOrigin: true },
      },
    },
  }
})
