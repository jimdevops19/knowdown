import { useState } from 'react'
import { Link } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { listMyMatches } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { useAuth } from '../features/auth/useAuth'
import { Avatar } from '../components/Avatar'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, Loading } from '../components/states'
import { timeAgo } from '../lib/format'
import type { MatchupSummary } from '../lib/api/types'

/*
 * `/matches` — your own history, newest first.
 *
 * Every row is a match you were in, so "you" and "them" is a matter of finding
 * yourself in the two-element `players` array rather than the API telling you
 * which side you are. That is deliberate on the backend's part: the same
 * serializer answers for both players, and neither gets a payload shaped around
 * them.
 */
export function MatchesPage() {
  const [page, setPage] = useState(1)
  const matches = useQuery({
    queryKey: queryKeys.matches.mine(page),
    queryFn: () => listMyMatches({ page }),
    placeholderData: keepPreviousData,
  })

  const pagination = matches.data?.pagination
  const rows = matches.data?.results ?? []

  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-2xl font-bold text-chalk">My matches</h1>

      {matches.isLoading && <Loading variant="rows" />}
      {matches.isError && <ErrorState error={matches.error} />}
      {matches.data && rows.length === 0 && (
        <EmptyState
          message="No matches yet. Your first one is one tap away."
          action={
            <Button as={Link} to="/">
              Find a match
            </Button>
          }
        />
      )}

      <div className="flex flex-col gap-2">
        {rows.map((match) => (
          <MatchRow key={match.id} match={match} />
        ))}
      </div>

      {pagination && pagination.pages > 1 && (
        <div className="flex items-center justify-between gap-3">
          <Button
            variant="secondary"
            size="sm"
            disabled={!pagination.previous}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </Button>
          <span className="nums text-sm text-ash">
            Page {pagination.page} of {pagination.pages}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={!pagination.next}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  )
}

function MatchRow({ match }: { match: MatchupSummary }) {
  const { user } = useAuth()
  const me = match.players.find((side) => side.player.id === user?.player_id)
  const them = match.players.find((side) => side.player.id !== user?.player_id)

  // A match still running is reachable — tapping it rejoins the live socket,
  // which is what a player who closed the tab by accident needs. Everything
  // else goes to the box score.
  const live = match.status === 'active' || match.status === 'waiting'
  const to = live ? `/match/${match.id}` : `/matches/${match.id}`

  return (
    <Card as={Link} to={to} interactive className="flex items-center gap-3 p-3.5">
      <Avatar
        name={them?.player.display_name ?? '?'}
        avatarUrl={them?.player.avatar_url}
        size={40}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-chalk">
          vs {them?.player.display_name ?? 'Unknown'}
        </p>
        <p className="text-xs text-ash">
          {match.category} · {match.question_count} questions ·{' '}
          {timeAgo(match.completed_at ?? match.started_at)}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <span className="nums font-display text-lg font-bold text-chalk">
          {me?.score ?? 0}
          <span className="mx-1 text-ash">–</span>
          <span className="text-ash">{them?.score ?? 0}</span>
        </span>
        <Outcome match={match} won={me?.is_winner ?? false} live={live} />
      </div>
    </Card>
  )
}

function Outcome({
  match,
  won,
  live,
}: {
  match: MatchupSummary
  won: boolean
  live: boolean
}) {
  if (live) return <StatusBadge tone="live">Live</StatusBadge>
  // Neither side flagged as the winner is the double tie the server leaves
  // unbroken — level on points and level on total answer time. Rare, and a real
  // outcome, so it says so rather than being rounded down to a loss.
  const drew = !match.players.some((side) => side.is_winner)
  if (drew) return <StatusBadge tone="draw">Draw</StatusBadge>
  return (
    <StatusBadge tone={won ? 'win' : 'loss'}>
      {won ? 'Won' : 'Lost'}
      {match.outcome === 'abandoned' && ' · left'}
    </StatusBadge>
  )
}
