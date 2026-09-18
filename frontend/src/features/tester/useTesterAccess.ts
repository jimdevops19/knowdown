import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '../../lib/query/queryClient'
import { useAuth } from '../auth/useAuth'
import { getTesterConfig } from './api'

/*
 * Whether this person, on this deployment, has a question tester.
 *
 * **It is asked, not inferred.** The two things that decide it — the backend
 * mounted the routes (`TESTER_ENDPOINT_ENABLED`) and this account is `is_staff`
 * — are both server-side, and neither is in the session this client holds. The
 * alternative would be putting `is_staff` on `/players/me/` so the client could
 * decide for itself, which is a new field on the app's most-fetched payload,
 * for every player, to answer a question about a handful of accounts.
 *
 * So the probe *is* the config call the page needs anyway: 200 means both gates
 * are open and the filter bar's vocabulary is already in hand.
 *
 * **A failure here is the normal case.** Almost every real user gets a 404 (the
 * tier did not mount it) or a 403 (not staff), and neither is an error anybody
 * should see — hence `retry: false` and a hook that reports a boolean rather
 * than an error. `queryClient` already refuses to retry a 4xx, and this states
 * it locally too, because the one failure that *is* transient (a 5xx while the
 * backend restarts) would otherwise put three retries behind every page load
 * for a nav item almost nobody has.
 */
export function useTesterAccess() {
  const { isAuthenticated } = useAuth()

  const query = useQuery({
    queryKey: queryKeys.tester.access,
    queryFn: getTesterConfig,
    // Signed out, the answer is no without asking — and asking would fire a
    // request on every public page in the app.
    enabled: isAuthenticated,
    staleTime: Infinity,
    retry: false,
  })

  return {
    /** True only once the server has said so. Never optimistic: the nav entry
     *  and the route both hang off this, and a tester link that 404s on tap is
     *  worse than no link. */
    available: query.isSuccess && query.data.enabled,
    /** Still asking. The page shows nothing rather than "no" during this —
     *  flashing "not available" at the one person who does have access, on
     *  every reload, would be the wrong half-second to be wrong in. */
    isLoading: isAuthenticated && query.isPending,
    config: query.data ?? null,
  }
}
