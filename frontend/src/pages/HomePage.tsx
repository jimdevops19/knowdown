import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Flame, Timer, Zap } from 'lucide-react'
import { getPlayerProfile, listMyMatches } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { useAuth } from '../features/auth/useAuth'
import { CategoryGrid } from '../features/play/CategoryGrid'
import { Avatar } from '../components/Avatar'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { SectionHeading } from '../components/SectionHeading'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, Loading } from '../components/states'
import { Logo } from '../components/Logo'
import { formatRecord, timeAgo, winRate } from '../lib/format'
import type { MatchupSummary } from '../lib/api/types'

/*
 * `/` — the way into a match, whether or not you're signed in.
 *
 * There is exactly one thing to do on this app, so the page is built around it:
 * pick a category, and the button under it starts a match. Everything else on
 * the screen — the rating, the record — is *why you would*, and sits below.
 *
 * Signed out it is the same page with the same category cards, and tapping one
 * routes through sign-in and back (see `RequireAuth`, which carries the
 * destination in `?next=`). A landing page that hides the product behind a
 * sign-up wall is a landing page nobody signs up from.
 */
export function HomePage() {
  const { isAuthenticated, user } = useAuth()

  return (
    <div className="flex flex-col gap-8 pb-4">
      {isAuthenticated ? <PlayerHero /> : <GuestHero />}

      <section className="flex flex-col gap-3">
        <SectionHeading>Pick your category</SectionHeading>
        <CategoryGrid />
      </section>

      {!isAuthenticated && <HowItWorks />}

      {isAuthenticated && user?.player_name && <YourStandings displayName={user.player_name} />}

      {isAuthenticated && <RecentMatches />}
    </div>
  )
}

function GuestHero() {
  return (
    <section className="flex flex-col items-center gap-4 py-6 text-center">
      <Logo size={44} />
      <h1 className="text-balance font-display text-3xl font-bold leading-tight text-chalk sm:text-4xl">
        Two players. <span className="text-gradient">Seven questions.</span> One clock.
      </h1>
      <p className="max-w-md text-balance text-ash">
        Everyone online sits in one pool. Get paired, race a stranger through NBA trivia, and take
        their rating when you're faster.
      </p>
    </section>
  )
}

/** The signed-in header: who you are, and the one button that matters. */
function PlayerHero() {
  const { user } = useAuth()
  return (
    <section className="flex items-center gap-4">
      <Avatar
        name={user?.player_name ?? '?'}
        seed={user?.player_id ?? undefined}
        avatarUrl={user?.player_avatar_url ?? null}
        size={56}
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm text-ash">Ready when you are</p>
        <h1 className="truncate font-display text-2xl font-bold text-chalk">
          {user?.player_name}
        </h1>
      </div>
    </section>
  )
}

const RULES = [
  { icon: Timer, title: '10 seconds a question', body: 'The server holds the clock. No timeouts you can argue with.' },
  { icon: Zap, title: 'Right, then fast', body: 'A wrong answer scores nothing however quick it was. Speed only multiplies a correct one.' },
  { icon: Flame, title: '3, 5 or 7 questions', body: "The length is drawn per match, so you never know which question is the last one." },
]

function HowItWorks() {
  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>How a match works</SectionHeading>
      <div className="grid gap-3 sm:grid-cols-3">
        {RULES.map(({ icon: Icon, title, body }) => (
          <Card key={title} className="flex flex-col gap-2 p-5">
            <Icon size={20} className="text-volt" aria-hidden />
            <h3 className="font-display font-bold text-chalk">{title}</h3>
            <p className="text-sm text-ash">{body}</p>
          </Card>
        ))}
      </div>
      <Button as={Link} to="/how-to-play" variant="ghost" size="full" className="mt-1">
        Read the full rules
      </Button>
    </section>
  )
}

/**
 * Your rating in every category you've played.
 *
 * Read from the public profile rather than from a "my stats" endpoint, because
 * there isn't one and shouldn't be: a profile is exactly this data, and having
 * one endpoint means what you see of yourself is what everybody else sees of
 * you. A player who has never finished a match has no rankings at all, which is
 * why the empty case is a prompt to play rather than a row of zeroes.
 */
function YourStandings({ displayName }: { displayName: string }) {
  const profile = useQuery({
    queryKey: queryKeys.players.profile(displayName),
    queryFn: () => getPlayerProfile(displayName),
  })

  if (profile.isLoading || !profile.data) return null
  const { rankings, badges } = profile.data
  if (rankings.length === 0) return null

  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>Where you stand</SectionHeading>
      <div className="grid gap-3 sm:grid-cols-2">
        {rankings.map((ranking) => (
          <Card key={ranking.category} className="flex items-center justify-between gap-3 p-4">
            <div className="min-w-0">
              <p className="truncate font-medium text-chalk">{ranking.category_name}</p>
              <p className="nums text-sm text-ash">
                {formatRecord(ranking.wins, ranking.losses)} · {winRate(ranking.wins, ranking.games_played)}
              </p>
            </div>
            <span className="nums shrink-0 font-display text-2xl font-bold text-gold">
              {ranking.rating}
            </span>
          </Card>
        ))}
      </div>
      {badges.length > 0 && (
        <Link to={`/players/${displayName}`} className="text-sm text-volt hover:underline">
          {badges.length} badge{badges.length === 1 ? '' : 's'} earned →
        </Link>
      )}
    </section>
  )
}

/** Your last 5 finished games, newest first — the quick "what just happened"
 *  a player checks the moment they land on Home, full history one tap away. */
function RecentMatches() {
  const { user } = useAuth()
  const matches = useQuery({
    queryKey: queryKeys.matches.mine(1),
    queryFn: () => listMyMatches({ page: 1, page_size: 5 }),
  })

  const rows = matches.data?.results ?? []

  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>Recent matches</SectionHeading>
      {matches.isLoading && <Loading variant="rows" />}
      {matches.isError && <ErrorState error={matches.error} />}
      {matches.data && rows.length === 0 && (
        <EmptyState message="No matches yet. Your first one is one tap away." />
      )}
      {rows.length > 0 && (
        <>
          <div className="flex flex-col gap-2">
            {rows.map((match) => (
              <RecentMatchRow key={match.id} match={match} playerId={user?.player_id ?? null} />
            ))}
          </div>
          <Link to="/matches" className="text-sm text-volt hover:underline">
            Full match history →
          </Link>
        </>
      )}
    </section>
  )
}

function RecentMatchRow({ match, playerId }: { match: MatchupSummary; playerId: string | null }) {
  const me = match.players.find((side) => side.player.id === playerId)
  const them = match.players.find((side) => side.player.id !== playerId)
  const drew = !match.players.some((side) => side.is_winner)

  return (
    <Card as={Link} to={`/matches/${match.id}`} interactive className="flex items-center gap-3 p-3.5">
      <Avatar name={them?.player.display_name ?? '?'} avatarUrl={them?.player.avatar_url} size={36} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-chalk">vs {them?.player.display_name ?? 'Unknown'}</p>
        <p className="text-xs text-ash">
          {match.category} · {timeAgo(match.completed_at ?? match.started_at)}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <span className="nums font-display text-base font-bold text-chalk">
          {me?.score ?? 0}
          <span className="mx-1 text-ash">–</span>
          <span className="text-ash">{them?.score ?? 0}</span>
        </span>
        {drew ? (
          <StatusBadge tone="draw">Draw</StatusBadge>
        ) : (
          <StatusBadge tone={me?.is_winner ? 'win' : 'loss'}>{me?.is_winner ? 'Won' : 'Lost'}</StatusBadge>
        )}
      </div>
    </Card>
  )
}
