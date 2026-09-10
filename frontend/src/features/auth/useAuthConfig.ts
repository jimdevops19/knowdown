import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '../../lib/query/queryClient'
import { getAuthConfig } from './api'
import { GOOGLE_CLIENT_ID } from '../../lib/config'

/*
 * What the sign-in screen has to know before it can draw itself.
 *
 * Two independent halves have to agree before a Google button is worth showing:
 * the *server* must have credentials (`google_enabled`) and this *client* must
 * have a client id to start the flow with. Either one missing is a button that
 * fails on tap, so `googleEnabled` is the conjunction, not the server's flag
 * alone.
 *
 * Cached for the session: a deployment does not gain a sign-in method while
 * somebody is looking at the form.
 */
export function useAuthConfig() {
  const query = useQuery({
    queryKey: queryKeys.auth.config,
    queryFn: getAuthConfig,
    staleTime: Infinity,
    // A config that cannot be fetched must not leave the screen blank. The
    // fallback is the conservative one — password auth on, Google off — because
    // showing a form that might 404 is recoverable, and hiding the only way in
    // is not.
    retry: 1,
  })

  const config = query.data
  return {
    isLoading: query.isLoading,
    passwordEnabled: config?.password_enabled ?? true,
    googleEnabled: (config?.google_enabled ?? false) && !!GOOGLE_CLIENT_ID,
  }
}
