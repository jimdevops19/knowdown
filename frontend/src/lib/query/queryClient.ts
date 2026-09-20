import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/errors'

/*
 * The React Query client. It caches server state and handles refetching and
 * retries so components don't manage loading flags by hand.
 *
 * Note what is *not* configured here: any kind of polling. In rpool the live
 * views poll as a fallback for a socket that has gone quiet, because its socket
 * messages are thin pointers and the REST endpoint is the real source. Here the
 * socket carries the game itself — the board, the clock, the verdict — and
 * there is no endpoint to fall back to. A dropped socket mid-question is a
 * reconnect (`lib/realtime/socket.ts`), which the server answers by re-sending
 * the question in progress and the time left on it.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Treat data as fresh for 30s before a background refetch is considered.
      staleTime: 30_000,
      // Don't retry client errors (4xx) — only transient ones, up to twice.
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status && error.status < 500) {
          return false
        }
        return failureCount < 2
      },
      refetchOnWindowFocus: false,
    },
  },
})

/*
 * Query keys, namespaced per feature and spelled in one place so an
 * invalidation and the query it means to invalidate cannot drift apart.
 *
 * `matches.detail` is invalidated by the end of a live match: the box score for
 * a matchup that was in progress when it was last fetched is now a different
 * document.
 */
export const queryKeys = {
  categories: {
    all: ['categories'] as const,
    detail: (slug: string) => ['categories', slug] as const,
  },
  rooms: {
    all: ['rooms'] as const,
    detail: (slug: string) => ['rooms', slug] as const,
  },
  players: {
    me: ['players', 'me'] as const,
    profile: (displayName: string) => ['players', 'profile', displayName] as const,
    nameAvailable: (name: string) => ['players', 'name-available', name] as const,
  },
  rankings: {
    ladder: (category: string, page: number) => ['rankings', category, page] as const,
  },
  matches: {
    mine: (page: number) => ['matches', 'mine', page] as const,
    detail: (id: string) => ['matches', 'detail', id] as const,
    participants: (id: string) => ['matches', 'participants', id] as const,
  },
  auth: {
    config: ['auth', 'config'] as const,
  },
  /* The maintainers' question tester. `access` is the probe that decides
   * whether the page and its nav entry exist at all, and it is cached for the
   * session: a deployment does not mount the tester, and an account does not
   * become staff, while somebody is looking at a list of questions. */
  tester: {
    access: ['tester', 'access'] as const,
    questions: (filters: unknown) => ['tester', 'questions', filters] as const,
    rehearsal: (type: string, id: string, seed: string) =>
      ['tester', 'rehearsal', type, id, seed] as const,
    /* The authored YAML behind one question — what the edit form is seeded
     * from. Its own key rather than a field on the rehearsal: a rehearsal is
     * the *row* staged for play, and these two disagree on purpose (the row
     * has had its file's clock resolved into it, the entry has not). */
    source: (type: string, id: string) => ['tester', 'source', type, id] as const,
  },
}
