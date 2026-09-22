import { useEffect } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getRoom } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { useMatchmaking } from '../lib/realtime'
import { useAuth } from '../features/auth/useAuth'
import { Searching } from '../features/play/Searching'
import { Button } from '../components/Button'
import { ErrorState, Loading } from '../components/states'

/*
 * `/play/:room` — join a room's pool and wait.
 *
 * The page exists for the length of one search. Mounting it queues the player;
 * leaving it, by any route, takes them out — so there is no state here to keep
 * in step with the server, and no way to end up queued in a room the player has
 * navigated away from.
 *
 * The room itself is fetched for one reason: the screen has to name what it is
 * searching in, and the slug ("nba-room-finals") is not that name. The search
 * does not wait on it — the socket opens on the slug from the URL, which is all
 * the server needs — so a slow lobby request delays the label, never the queue.
 *
 * When a pairing lands it navigates to the match and **replaces** the history
 * entry. Back from a live match should go to where the player came from, not to
 * a search screen that would immediately re-queue them for a second match while
 * the first one is still running.
 *
 * ── Cancelling puts the player back where they were ─────────────────────────
 * Cancel used to go to `/`, which is wrong for the common path: the lobby is
 * on `/play` as well as on Home, and a player who picked a ball on the Play tab
 * and changed their mind was moved to a different screen for it. Backing out of
 * a choice should return you to the menu you made it from, so the tile that
 * opened this search says where it was (`RoomCircles` puts `state.from` on the
 * link) and Cancel goes back there.
 *
 * `/play` is the fallback rather than `/`, and it is the answer for every
 * entrance that carries no origin: a deep link, a refresh (React Router does
 * keep history state across one, but a pasted URL has none), and the detour
 * through sign-in, which comes back via `?next=` and cannot bring state with
 * it. All of those are a player who has no previous screen in this app, and
 * the lobby is the one place a cancelled search is certainly still useful.
 *
 * `navigate(-1)` would be the same thing for one of those cases and wrong for
 * the rest — with no history to pop it leaves the player on the search screen,
 * still queued.
 */
export function PlayPage() {
  const { room = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  // Where the tile that started this search was tapped — see the header.
  const from = (location.state as { from?: unknown } | null)?.from
  const origin = typeof from === 'string' && from.startsWith('/') ? from : '/play'
  const { user } = useAuth()

  const lobby = useQuery({
    queryKey: queryKeys.rooms.detail(room),
    queryFn: () => getRoom(room),
    enabled: Boolean(room),
    staleTime: Infinity,
  })

  const search = useMatchmaking(room || null)

  useEffect(() => {
    if (search.phase === 'found' && search.matchupId) {
      // `?from=` is the room to come back to — the "Play again" button on the
      // summary screen is the only reader.
      navigate(`/match/${search.matchupId}?from=${encodeURIComponent(room)}`, { replace: true })
    }
  }, [search.phase, search.matchupId, navigate, room])

  const name = lobby.data?.name ?? room

  if (search.phase === 'failed') {
    return (
      <div className="mx-auto flex w-full max-w-sm flex-col gap-4 py-8">
        <ErrorState error={new Error(search.error ?? 'The search ended unexpectedly.')} />
        <Button size="full" onClick={() => navigate(0)}>
          Try again
        </Button>
        <Button variant="ghost" size="full" onClick={() => navigate(origin)}>
          Back to rooms
        </Button>
      </div>
    )
  }

  // 'connecting' and 'found' both show the search: the first because the queue
  // is a moment away, the second because the redirect above is already in
  // flight and flashing a different screen for one frame would be worse than
  // holding this one.
  if (search.phase === 'connecting' && lobby.isLoading) {
    return <Loading label="Opening the room…" />
  }

  return (
    <Searching
      roomName={name}
      displayName={user?.player_name ?? 'You'}
      mascot={user?.player_mascot ?? null}
      playerId={user?.player_id ?? null}
      waitingSeconds={search.waitingSeconds}
      onCancel={() => {
        search.cancel()
        navigate(origin, { replace: true })
      }}
    />
  )
}
