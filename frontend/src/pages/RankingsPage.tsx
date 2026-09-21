import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { LockKeyhole } from 'lucide-react'
import { getLadder, listCategories } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { useAuth } from '../features/auth/useAuth'
import { Avatar } from '../components/Avatar'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { RankingsNumberDisplay } from '../components/RankingsNumberDisplay'
import { SectionHeading } from '../components/SectionHeading'
import { EmptyState, ErrorState, Loading } from '../components/states'
import { formatRecord, ordinal, winRate } from '../lib/format'
import type { LadderEntry } from '../lib/api/types'

/*
 * `/rankings` and `/rankings/:category` — the ladder.
 *
 * Signed-in only: the nav hides the tab from a guest (see `navItems`), but the
 * URL itself still resolves, so a guest who reaches it directly — a shared
 * link, a bookmark, typing it in — gets a sign-in prompt in place of the
 * ladder rather than a route that 404s or silently leaks the data.
 *
 * `keepPreviousData` on the page query, so paging holds the current rows in
 * place while the next ones load rather than collapsing the list to a skeleton
 * and back — on a phone that collapse moves the whole page under a thumb that
 * is already reaching for the next button.
 */
export function RankingsPage() {
  const { category: routeCategory } = useParams()
  const { isAuthenticated, user } = useAuth()
  const location = useLocation()
  const [page, setPage] = useState(1)

  const categories = useQuery({
    queryKey: queryKeys.categories.all,
    queryFn: listCategories,
    staleTime: Infinity,
    enabled: isAuthenticated,
  })

  // No category in the URL means the first one — knowdown ships with NBA and
  // is built to grow more, so the picker exists from the start rather than
  // being retrofitted when the second category lands.
  const category = routeCategory ?? categories.data?.[0]?.slug

  const ladder = useQuery({
    queryKey: queryKeys.rankings.ladder(category ?? '', page),
    queryFn: () => getLadder(category!, { page }),
    enabled: isAuthenticated && !!category,
    placeholderData: keepPreviousData,
  })

  const pagination = ladder.data?.pagination
  const rows = ladder.data?.results ?? []
  // The page's rows are numbered from where the page starts, so row 1 of page 3
  // is 51st and not 1st.
  const offset = pagination ? (pagination.page - 1) * pagination.page_size : 0

  if (!isAuthenticated) {
    const next = encodeURIComponent(location.pathname + location.search)
    return (
      <Card className="flex flex-col items-center gap-4 p-10 text-center">
        <LockKeyhole className="text-ash/60" size={28} />
        <p className="text-ash">Sign in to see rankings</p>
        <Button as={Link} to={`/login?next=${next}`}>
          Sign in
        </Button>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3">
        <h1 className="font-display text-2xl font-bold text-chalk">Rankings</h1>
        {/* Shown from the first category rather than from the second. A picker
            that appears only once a second ladder exists is a control nobody
            has seen before the day it matters, and it hides the fact that a
            rating is *per category* — which is the one thing a player has to
            understand to read this page at all. With one category it is a
            single tab saying what you are looking at. */}
        {categories.data && categories.data.length > 0 && (
          <div className="flex gap-2 overflow-x-auto scrollbar-none">
            {categories.data.map((option) => (
              <Link
                key={option.slug}
                to={`/rankings/${option.slug}`}
                onClick={() => setPage(1)}
                className={`shrink-0 rounded-btn border px-3 py-1.5 font-display text-sm font-semibold transition-colors ${
                  option.slug === category
                    ? 'border-court bg-court/20 text-chalk'
                    : 'border-chalk/10 text-ash hover:text-chalk'
                }`}
              >
                {option.name}
              </Link>
            ))}
          </div>
        )}
      </div>

      {ladder.isLoading && <Loading variant="rows" />}
      {ladder.isError && <ErrorState error={ladder.error} />}
      {ladder.data && rows.length === 0 && (
        <EmptyState
          message="Nobody has finished a ranked match here yet."
          // The lobby, not `/play/{category}`: that route's slug is a *room*
          // (see `useMatchmaking`, which opens `/ws/v1/matchmaking/room/…`),
          // so a category slug there is a queue the server refuses. Which of
          // this category's rooms to enter is a choice the lobby already
          // presents.
          action={
            <Button as={Link} to="/play">
              Be the first
            </Button>
          }
        />
      )}

      {rows.length > 0 && (
        <>
          <SectionHeading>{pagination?.count ?? rows.length} ranked players</SectionHeading>
          <ol className="flex flex-col gap-2">
            {rows.map((entry, index) => (
              <LadderRow
                key={entry.player.id}
                entry={entry}
                position={offset + index + 1}
                isMe={entry.player.id === user?.player_id}
              />
            ))}
          </ol>
        </>
      )}

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

function LadderRow({
  entry,
  position,
  isMe,
}: {
  entry: LadderEntry
  position: number
  isMe: boolean
}) {
  return (
    <li>
      <Link
        to={`/players/${entry.player.display_name}`}
        className={`flex items-center gap-3 rounded-card border px-3 py-3 transition-colors ${
          isMe
            ? 'bg-row-highlight border-volt/50'
            : 'border-chalk/6 bg-panel/70 hover:border-chalk/15'
        }`}
      >
        <span className="shrink-0">
          <RankingsNumberDisplay rank={position} size={32} />
          <span className="sr-only">
            {position} — {ordinal(position)}
          </span>
        </span>
        <Avatar
          name={entry.player.display_name}
          mascot={entry.player.mascot}
          size={36}
          ring={isMe}
        />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-chalk">
            {entry.player.display_name}
            {isMe && <span className="ml-2 text-xs font-normal text-volt">you</span>}
          </p>
          <p className="nums text-xs text-ash">
            {formatRecord(entry.wins, entry.losses)} · {winRate(entry.wins, entry.games_played)} win
            rate
          </p>
        </div>
        <span className="nums shrink-0 font-display text-xl font-bold text-chalk">
          {entry.rating}
        </span>
      </Link>
    </li>
  )
}
