import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load .env* so VITE_PROXY_TARGET set there reaches the dev proxy below. A
  // real process env var of the same name still wins (loadEnv merges it in).
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000'

  return {
    // Tailwind v4 plugs straight into Vite — no separate config file and no
    // PostCSS setup; the whole theme lives in CSS (see src/index.css).
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
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
