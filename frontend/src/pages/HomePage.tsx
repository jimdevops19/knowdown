import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Flame, Timer, Zap } from 'lucide-react'
import { getPlayerProfile, listMyMatches } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { useAuth } from '../features/auth/useAuth'
import { RoomCircles } from '../features/play/RoomCircles'
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
 * pick a room — the settings a match is played under — and tapping it starts
 * the search. Everything else on the screen — the rating, the record — is *why
 * you would*, and sits below.
 *
 * Signed out it is the same page with the same room circles, and tapping one
 * routes through sign-in and back (see `RequireAuth`, which carries the
 * destination in `?next=`). A landing page that hides the product behind a
 * sign-up wall is a landing page nobody signs up from.
 */
export function HomePage() {
  const { isAuthenticated, user } = useAuth()

  return (
    <div className="flex flex-col gap-6 pb-4 sm:gap-8">
      {isAuthenticated ? <PlayerHero /> : <GuestHero />}

      <section className="flex flex-col gap-5">
        <SectionHeading>Pick a room</SectionHeading>
        <RoomCircles />
      </section>

      {!isAuthenticated && <HowItWorks />}

      {isAuthenticated && user?.player_name && <YourStandings displayName={user.player_name} />}

      {isAuthenticated && <RecentMatches />}
    </div>
  )
}

/*
 * The signed-out hero — a title card, not a landing page.
 *
 * What this replaces was a centred stack: logo, one balanced sentence, one
 * paragraph of grey text under it. That arrangement is the single most
 * reproduced layout on the web and the first thing that marks a page as
 * generated, and it is also weak for this particular product — a centred line
 * of running text gives no emphasis to the three facts that actually sell the
 * game.
 *
 * So the sentence is broken into its three beats and stacked, each on its own
 * line, in widened display caps at a size that fills the column. Read down, it
 * is a broadcast title card. The rule and the small orange label above it are
 * the lower-third furniture that goes with it, and the whole block is
 * left-aligned, because a hard left edge is what makes stacked type read as
 * deliberate rather than as a heading that wrapped.
 */
function GuestHero() {
  return (
    <section className="flex flex-col gap-4 py-1 sm:gap-5 sm:py-4">
      {/* Wraps rather than squeezes: on a narrow phone the strap drops onto its
          own line under the wordmark instead of the two fighting over the row.
          `whitespace-nowrap` keeps it from breaking *within* itself — a strap
          this heavily tracked splits into two unreadable fragments. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Logo size={36} />
        {/* The brand orange, small and tracked wide: the "LIVE" bug in the corner of a
            broadcast. It is a label, so it takes caps; body copy never does. */}
        <span className="whitespace-nowrap text-xs font-semibold uppercase tracking-[0.22em] text-volt">
          Live 1v1 trivia
        </span>
      </div>

      {/*
        The size is set from the *longest* line, not from taste. The beats are
        hard-broken with <br>, so the block only reads as a title card while
        each line still fits its column — let one wrap and the stack collapses
        into an ordinary paragraph of shouting.

        "Someone random." in widened caps is the widest thing this app renders,
        and 1.75rem is the size at which it just fills a 390px phone. Anything
        larger has to come with a smaller step below it, which is what the
        breakpoints here are: one size per width, each the largest that still
        fits its own narrowest case.
      */}
      <h1 className="text-headline text-[1.75rem] leading-[0.94] text-chalk min-[420px]:text-[2.1rem] sm:text-5xl lg:text-6xl">
        You vs.
        <br />
        Someone random.
        {/* The payoff sentence takes the primary — the one beat of colour in
            the block. Both of its beats are shorter than "Someone random.", so
            it stays at the headline size. It breaks as a block rather than on a
            <br> so the colour change gets a beat of air ahead of it — at 0.94
            leading the two halves otherwise read as one four-line paragraph.
            The gap is in `em`, so it scales with the heading at every step. */}
        <span className="mt-[0.3em] block text-court">
          Just trivia,
          <br />
          and adrenaline.
        </span>
      </h1>

      <div className="h-px w-full bg-chalk/10" />

      <p className="max-w-md text-ash">
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

/*
 * The rules, as a rulebook rather than as three cards in a row.
 *
 * Three equal bordered cards, each with a thin-line icon above a bold title
 * above two lines of grey — that is the feature triptych, and it is the layout
 * tell that sits right beside the purple one. It is also doing nothing for the
 * content: these are three *rules*, which is a list, and a list wants a
 * vertical rhythm and an index, not three floating boxes.
 *
 * So: one plate, rules stacked inside it, each numbered in widened display
 * type against a ruled divider. The number is the ordering the content already
 * has. The icon moves to the right margin, where it annotates rather than
 * announces.
 */
function HowItWorks() {
  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>How a match works</SectionHeading>
      <Card className="flex flex-col divide-y divide-chalk/8">
        {RULES.map(({ icon: Icon, title, body }, i) => (
          <div key={title} className="flex items-start gap-4 p-5">
            <span className="nums w-6 shrink-0 pt-0.5 font-display text-lg font-bold [font-stretch:var(--display-wide)] text-court">
              {i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <h3 className="font-display font-bold text-chalk">{title}</h3>
              <p className="mt-1 text-sm text-ash">{body}</p>
            </div>
            <Icon size={18} className="mt-1 shrink-0 text-idle" aria-hidden />
          </div>
        ))}
      </Card>
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
