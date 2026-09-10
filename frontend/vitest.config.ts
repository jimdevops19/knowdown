import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

/*
 * Vitest lives in its own config rather than a `test` block on vite.config.ts:
 * that file is the *dev/build* config — the dev proxy, Tailwind — and none of
 * it has anything to say about a jsdom test run. The React plugin is the only
 * piece the tests actually need (JSX), so it is the only one here.
 *
 * Tests sit next to the code they cover as `*.test.ts(x)`, not in a parallel
 * tree, so a module and its test move together.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
