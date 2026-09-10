import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { getLadder, listCategories } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { useAuth } from '../features/auth/useAuth'
import { Avatar } from '../components/Avatar'
import { Button } from '../components/Button'
import { SectionHeading } from '../components/SectionHeading'
import { EmptyState, ErrorState, Loading } from '../components/states'
import { formatRecord, ordinal, winRate } from '../lib/format'
import type { LadderEntry } from '../lib/api/types'

/*
 * `/rankings` and `/rankings/:category` — the ladder.
 *
 * Public, like the profile it links to: a rating is what a scoreboard already
 * shows both players mid-match, made reachable on its own.
 *
 * `keepPreviousData` on the page query, so paging holds the current rows in
 * place while the next ones load rather than collapsing the list to a skeleton
 * and back — on a phone that collapse moves the whole page under a thumb that
 * is already reaching for the next button.
 */
export function RankingsPage() {
  const { category: routeCategory } = useParams()
  const { user } = useAuth()
  const [page, setPage] = useState(1)

  const categories = useQuery({
    queryKey: queryKeys.categories.all,
    queryFn: listCategories,
    staleTime: Infinity,
  })

  // No category in the URL means the first one — knowdown ships with NBA and
  // is built to grow more, so the picker exists from the start rather than
  // being retrofitted when the second category lands.
  const category = routeCategory ?? categories.data?.[0]?.slug

  const ladder = useQuery({
    queryKey: queryKeys.rankings.ladder(category ?? '', page),
    queryFn: () => getLadder(category!, { page }),
    enabled: !!category,
    placeholderData: keepPreviousData,
  })

  const pagination = ladder.data?.pagination
  const rows = ladder.data?.results ?? []
  // The page's rows are numbered from where the page starts, so row 1 of page 3
  // is 51st and not 1st.
  const offset = pagination ? (pagination.page - 1) * pagination.page_size : 0

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3">
        <h1 className="font-display text-2xl font-bold text-chalk">Rankings</h1>
        {categories.data && categories.data.length > 1 && (
          <div className="flex gap-2 overflow-x-auto scrollbar-none">
            {categories.data.map((option) => (
              <Link
                key={option.slug}
                to={`/rankings/${option.slug}`}
                onClick={() => setPage(1)}
                className={`shrink-0 rounded-btn border px-3 py-1.5 font-display text-sm font-semibold transition-colors ${
                  option.slug === category
                    ? 'border-court bg-court/20 text-chalk'
                    : 'border-white/10 text-ash hover:text-chalk'
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
          action={
            category && (
              <Button as={Link} to={`/play/${category}`}>
                Be the first
              </Button>
            )
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
  // Gold only for the actual podium. A ladder where a dozen rows are gold is a
  // ladder where gold means nothing — the whole point of the token is that it
  // is scarce.
  const podium = position <= 3

  return (
    <li>
      <Link
        to={`/players/${entry.player.display_name}`}
        className={`flex items-center gap-3 rounded-card border px-3 py-3 transition-colors ${
          isMe
            ? 'bg-row-highlight border-volt/50'
            : 'border-white/6 bg-panel/70 hover:border-white/15'
        }`}
      >
        <span
          className={`nums w-9 shrink-0 text-center font-display text-sm font-bold ${
            podium ? 'text-gold' : 'text-ash'
          }`}
        >
          {position}
          <span className="sr-only"> — {ordinal(position)}</span>
        </span>
        <Avatar
          name={entry.player.display_name}
          avatarUrl={entry.player.avatar_url}
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
