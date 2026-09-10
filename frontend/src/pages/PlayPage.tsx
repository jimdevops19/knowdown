import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { listCategories } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { useMatchmaking } from '../lib/realtime'
import { useAuth } from '../features/auth/useAuth'
import { Searching } from '../features/play/Searching'
import { Button } from '../components/Button'
import { ErrorState, Loading } from '../components/states'

/*
 * `/play/:category` — join the pool and wait.
 *
 * The page exists for the length of one search. Mounting it queues the player;
 * leaving it, by any route, takes them out — so there is no state here to keep
 * in step with the server, and no way to end up queued in a category the player
 * has navigated away from.
 *
 * When a pairing lands it navigates to the match and **replaces** the history
 * entry. Back from a live match should go to where the player came from, not to
 * a search screen that would immediately re-queue them for a second match while
 * the first one is still running.
 */
export function PlayPage() {
  const { category = '' } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()

  const categories = useQuery({
    queryKey: queryKeys.categories.all,
    queryFn: listCategories,
    staleTime: Infinity,
  })

  const search = useMatchmaking(category || null)

  useEffect(() => {
    if (search.phase === 'found' && search.matchupId) {
      navigate(`/match/${search.matchupId}?from=${encodeURIComponent(category)}`, { replace: true })
    }
  }, [search.phase, search.matchupId, navigate, category])

  const name = categories.data?.find((c) => c.slug === category)?.name ?? category

  if (search.phase === 'failed') {
    return (
      <div className="mx-auto flex w-full max-w-sm flex-col gap-4 py-8">
        <ErrorState error={new Error(search.error ?? 'The search ended unexpectedly.')} />
        <Button size="full" onClick={() => navigate(0)}>
          Try again
        </Button>
        <Button variant="ghost" size="full" onClick={() => navigate('/')}>
          Back home
        </Button>
      </div>
    )
  }

  // 'connecting' and 'found' both show the search: the first because the queue
  // is a moment away, the second because the redirect above is already in
  // flight and flashing a different screen for one frame would be worse than
  // holding this one.
  if (search.phase === 'connecting' && categories.isLoading) {
    return <Loading label="Opening the pool…" />
  }

  return (
    <Searching
      categoryName={name}
      displayName={user?.player_name ?? 'You'}
      avatarUrl={user?.player_avatar_url ?? null}
      playerId={user?.player_id ?? null}
      waitingSeconds={search.waitingSeconds}
      onCancel={() => {
        search.cancel()
        navigate('/', { replace: true })
      }}
    />
  )
}
