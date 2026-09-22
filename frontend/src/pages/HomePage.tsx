import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Flame, Timer, Zap } from 'lucide-react'
import { getLadder, getPlayerProfile, listMyMatches } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { useAuth } from '../features/auth/useAuth'
import { summarisePlayerForm, type MatchResult, type PlayerForm } from '../features/home/playerForm'
import { Avatar } from '../components/Avatar'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { SectionHeading } from '../components/SectionHeading'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, Loading } from '../components/states'
import { Logo } from '../components/Logo'
import { formatRecord, formatResponseTime, ordinal, timeAgo, winRate } from '../lib/format'
import type { MatchupSummary, PlayerProfile, Ranking } from '../lib/api/types'

/*
 * `/` — what the game has to say about *you*.
 *
 * This page used to open with the room circles, which is the one thing on it
 * that was already somewhere else: `/play` is the lobby, it is a tap away in
 * the nav, and a second copy of it here meant the first screen of the app was
 * a duplicate. A player who is signed in does not need to be re-offered the
 * lobby before they have been told anything — they came back to find out what
 * happened, and whether they are on a run.
 *
 * So home is now the **dashboard**: form, streak, the numbers a match produces
 * (accuracy, answer speed, points), where you stand on each ladder, the badges
 * you hold, and the last few results — with one button into the lobby at the
 * top rather than the lobby itself. Signed out it is unchanged in purpose: a
 * title card, the rules, and the same one button, because a landing page that
 * hides the product behind a sign-up wall is one nobody signs up from.
 *
 * Everything on it comes from two reads the app already makes — the public
 * profile and the caller's own match history. Nothing here is a new endpoint:
 * the derived numbers are `features/home/playerForm`, computed from the rows
 * `GET /matches/` already sends, and the rating is left to the server because
 * the server is the one that owns it.
 */

/** How many finished matches the form and the totals are measured over. One
 *  read, two uses: the strip shows the newest `FORM_LENGTH` of them and the
 *  recent list the newest five. */
const HISTORY_WINDOW = 20
const FORM_LENGTH = 10

export function HomePage() {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <PlayerHome /> : <GuestHome />
}

/* --- Signed in ------------------------------------------------------------- */

function PlayerHome() {
  const { user } = useAuth()
  const displayName = user?.player_name ?? null

  const matches = useQuery({
    queryKey: queryKeys.matches.recent(HISTORY_WINDOW),
    queryFn: () => listMyMatches({ page: 1, page_size: HISTORY_WINDOW }),
  })
  const profile = useQuery({
    queryKey: queryKeys.players.profile(displayName ?? ''),
    queryFn: () => getPlayerProfile(displayName as string),
    enabled: !!displayName,
  })

  const rows = matches.data?.results ?? []
  const form = summarisePlayerForm(rows, user?.player_id ?? null)

  return (
    <div className="flex flex-col gap-6 pb-4 sm:gap-8">
      <PlayerHero profile={profile.data} />

      <Button as={Link} to="/play" variant="accent" size="full">
        Find a match
      </Button>

      {form.played > 0 && <FormStrip form={form} />}
      {form.played > 0 && <StatTiles form={form} />}

      <YourStandings profile={profile.data} />
      <BadgeShelf profile={profile.data} displayName={displayName} />

      <RecentMatches
        rows={rows.slice(0, 5)}
        isLoading={matches.isLoading}
        error={matches.isError ? matches.error : null}
      />
    </div>
  )
}

/**
 * Who you are, your record, and the rating it earned.
 *
 * The line under the name is the **career** record, summed across every ladder
 * the profile carries — the server's own totals, not a count of the twenty
 * matches this page happens to have read. It used to be the current streak,
 * which was a mistake of a specific kind: "One loss so far" is a true sentence
 * about a run and a false-looking one about a record, and the slot directly
 * under a player's name is read as a record. The run is still shown, in the
 * form strip below, where ten results sitting beside it say what it means.
 *
 * The rating sits on the right, in gold — the colour this app reserves for
 * rank — with the ladder position under it when there is one.
 */
function PlayerHero({ profile }: { profile?: PlayerProfile }) {
  const { user } = useAuth()
  const top = topRanking(profile)

  return (
    <section className="flex items-center gap-4">
      <Avatar
        name={user?.player_name ?? '?'}
        seed={user?.player_id ?? undefined}
        mascot={user?.player_mascot ?? null}
        size={56}
      />
      <div className="min-w-0 flex-1">
        <h1 className="truncate font-display text-2xl font-bold text-chalk">
          {user?.player_name}
        </h1>
        <p className="nums truncate text-sm text-ash">{recordLine(profile)}</p>
      </div>
      {top && <StandingReadout ranking={top} />}
    </section>
  )
}

/** The best rating a player holds, which is the one the hero shows. A player
 *  ranked in three categories has three ratings and no single "their rating" —
 *  the highest is the one they would quote. */
function topRanking(profile?: PlayerProfile): Ranking | null {
  if (!profile || profile.rankings.length === 0) return null
  return profile.rankings.reduce((best, r) => (r.rating > best.rating ? r : best))
}

/** The career record, summed over every category the player is ranked in.
 *  Ranked matches only, because a rating is the only thing that keeps a running
 *  total — an unranked room (a CPU opponent, a mixed room) moves no ladder and
 *  so appears in the history below but not in this line. */
function recordLine(profile?: PlayerProfile): string {
  if (!profile || profile.rankings.length === 0) return 'Ready when you are'
  const wins = profile.rankings.reduce((n, r) => n + r.wins, 0)
  const losses = profile.rankings.reduce((n, r) => n + r.losses, 0)
  const played = profile.rankings.reduce((n, r) => n + r.games_played, 0)
  if (played === 0) return 'Ready when you are'
  return `${formatRecord(wins, losses)} · ${winRate(wins, played)} of ${played} ranked`
}

/** Rating, and the rung it puts you on. */
function StandingReadout({ ranking }: { ranking: Ranking }) {
  const standing = useLadderStanding(ranking.category)
  return (
    <div className="shrink-0 text-right">
      <p className="nums font-display text-2xl font-bold leading-none text-gold">
        {ranking.rating}
      </p>
      <p className="mt-1 text-xs text-ash">
        {standing ? standing : ranking.category_name}
      </p>
    </div>
  )
}

/**
 * Where one rating sits on its ladder — "3rd of 214".
 *
 * The head of the ladder only: the API paginates it, and walking every page to
 * find a player who is 400th would be a dozen requests for a line of text. A
 * player outside the head is told how many people are on the ladder instead,
 * which is the honest version of the same sentence — `count` is the ladder's
 * real size, not the size of the page read.
 */
const STANDING_WINDOW = 100

function useLadderStanding(category: string): string | null {
  const { user } = useAuth()
  const ladder = useQuery({
    queryKey: queryKeys.rankings.standing(category),
    queryFn: () => getLadder(category, { page: 1, page_size: STANDING_WINDOW }),
  })
  if (!ladder.data) return null
  const total = ladder.data.pagination?.count ?? ladder.data.results.length
  const index = ladder.data.results.findIndex((row) => row.player.id === user?.player_id)
  if (index < 0) return `of ${total} ranked`
  return `${ordinal(index + 1)} of ${total}`
}

const RESULT_CHIP: Record<MatchResult, { className: string; letter: string; label: string }> = {
  win: { className: 'bg-correct/18 text-correct', letter: 'W', label: 'Won' },
  loss: { className: 'bg-chalk/8 text-ash', letter: 'L', label: 'Lost' },
  draw: { className: 'bg-chalk/14 text-chalk', letter: 'D', label: 'Drew' },
}

/**
 * The last ten results as one row of letters, newest first.
 *
 * A form guide rather than a chart: ten squares is the whole of it, it reads in
 * one glance from either end, and it is the shape every league table on the
 * planet already uses for this. Newest first because the page is read
 * left-to-right from the side the player's eye starts on, and because it puts
 * the current streak — the thing the hero just claimed — first.
 */
function FormStrip({ form }: { form: PlayerForm }) {
  const results = form.results.slice(0, FORM_LENGTH)
  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>Recent form</SectionHeading>
      <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex gap-1.5">
          {results.map((result, i) => {
            const chip = RESULT_CHIP[result]
            return (
              <span
                key={i}
                title={chip.label}
                className={`flex h-7 w-7 items-center justify-center rounded-tile font-display text-xs font-bold ${chip.className}`}
              >
                <span className="sr-only">{chip.label}</span>
                <span aria-hidden>{chip.letter}</span>
              </span>
            )
          })}
        </div>
        <div className="flex flex-col items-end gap-1">
          <p className="nums text-sm text-ash">
            {formatRecord(form.wins, form.losses)}
            {form.draws > 0 && <span> · {form.draws}D</span>} in the last {form.played}
          </p>
          {/* Only a *run* is worth saying out loud. A streak of one is just the
              last result, which the first chip already shows. */}
          {form.streak && form.streak.length > 1 && form.streak.result !== 'draw' && (
            <StatusBadge tone={form.streak.result === 'win' ? 'win' : 'loss'}>
              {form.streak.length} {form.streak.result === 'win' ? 'in a row' : 'straight losses'}
            </StatusBadge>
          )}
        </div>
      </Card>
    </section>
  )
}

/**
 * The four numbers a match actually produces, none of which the app was
 * showing anywhere: how often you win, how much of a board you get right, how
 * long you take to answer one question, and what a good night looks like.
 *
 * Accuracy and speed are deliberately separate tiles. The scoring curve
 * multiplies them together (`apps.matches.constants.score_answer` — a wrong
 * answer is worth nothing however fast it was), so a player improving at this
 * game needs to know which of the two is the one holding them back.
 */
function StatTiles({ form }: { form: PlayerForm }) {
  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>Your numbers</SectionHeading>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Win rate" value={form.winRate === null ? '—' : `${form.winRate}%`} />
        <StatTile
          label="Accuracy"
          value={form.accuracy === null ? '—' : `${form.accuracy}%`}
          hint="of questions asked"
        />
        <StatTile
          label="Avg answer"
          value={form.avgAnswerMs === null ? '—' : formatResponseTime(form.avgAnswerMs)}
          hint="per question"
        />
        <StatTile
          label="Best score"
          value={form.bestScore === null ? '—' : String(form.bestScore)}
          hint={form.avgPoints === null ? undefined : `avg ${form.avgPoints}`}
        />
      </div>
      <p className="text-xs text-ash/70">
        Measured over your last {form.played} match{form.played === 1 ? '' : 'es'}.
      </p>
    </section>
  )
}

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="flex flex-col gap-1 p-4">
      <p className="font-display text-[11px] font-bold uppercase tracking-[0.12em] text-ash">
        {label}
      </p>
      <p className="nums font-display text-2xl font-bold leading-none text-chalk">{value}</p>
      {hint && <p className="nums text-xs text-ash/70">{hint}</p>}
    </Card>
  )
}

/**
 * Your rating in every category you've played.
 *
 * Read from the public profile rather than from a "my stats" endpoint, because
 * there isn't one and shouldn't be: a profile is exactly this data, and having
 * one endpoint means what you see of yourself is what everybody else sees of
 * you. A player who has never finished a ranked match has no rankings at all,
 * which is why the empty case is a prompt to play rather than a row of zeroes.
 */
function YourStandings({ profile }: { profile?: PlayerProfile }) {
  if (!profile || profile.rankings.length === 0) return null

  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>Where you stand</SectionHeading>
      <div className="grid gap-3 sm:grid-cols-2">
        {profile.rankings.map((ranking) => (
          <Card
            key={ranking.category}
            as={Link}
            to={`/rankings/${ranking.category}`}
            interactive
            edge="gold"
            className="flex items-center justify-between gap-3 p-4"
          >
            <div className="min-w-0">
              <p className="truncate font-medium text-chalk">{ranking.category_name}</p>
              <p className="nums text-sm text-ash">
                {formatRecord(ranking.wins, ranking.losses)} ·{' '}
                {winRate(ranking.wins, ranking.games_played)} of {ranking.games_played}
              </p>
            </div>
            <span className="nums shrink-0 font-display text-2xl font-bold text-gold">
              {ranking.rating}
            </span>
          </Card>
        ))}
      </div>
    </section>
  )
}

/**
 * The badges you hold, as the things they are — small marks in a row — rather
 * than as the line of text ("3 badges earned →") this used to be. A badge is
 * the only part of the game that is *collected*, so the page should show the
 * collection; the full descriptions live on the profile.
 */
function BadgeShelf({
  profile,
  displayName,
}: {
  profile?: PlayerProfile
  displayName: string | null
}) {
  if (!profile || !displayName) return null
  const badges = profile.badges

  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>Badges</SectionHeading>
      {badges.length === 0 ? (
        <Card className="p-4">
          <p className="text-sm text-ash">
            None yet. They're earned by what happens in a match — a clean sweep, a win over a
            higher-rated player — not by playing a number of them.
          </p>
        </Card>
      ) : (
        <Card as={Link} to={`/players/${displayName}`} interactive edge="gold" className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            {badges.slice(0, 8).map((badge) => (
              <span key={badge.slug} title={`${badge.name} — ${badge.description}`}>
                {badge.icon_url ? (
                  <img src={badge.icon_url} alt={badge.name} className="h-10 w-10 object-contain" />
                ) : (
                  <span className="flex h-10 w-10 items-center justify-center rounded-tile bg-gold/15 font-display text-base font-bold text-gold">
                    {badge.name[0]?.toUpperCase()}
                    <span className="sr-only">{badge.name}</span>
                  </span>
                )}
              </span>
            ))}
            {badges.length > 8 && (
              <span className="nums text-sm text-ash">+{badges.length - 8}</span>
            )}
          </div>
          <p className="mt-3 text-sm text-volt">
            {badges.length} badge{badges.length === 1 ? '' : 's'} earned →
          </p>
        </Card>
      )}
    </section>
  )
}

/** Your last 5 finished games, newest first — the quick "what just happened"
 *  a player checks the moment they land on Home, full history one tap away.
 *  Rendered from the same read the numbers above are computed from, so the
 *  page makes one request for both rather than two for the same rows. */
function RecentMatches({
  rows,
  isLoading,
  error,
}: {
  rows: MatchupSummary[]
  isLoading: boolean
  error: unknown
}) {
  const { user } = useAuth()

  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>Recent matches</SectionHeading>
      {isLoading && <Loading variant="rows" />}
      {error != null && <ErrorState error={error} />}
      {!isLoading && !error && rows.length === 0 && (
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
      <Avatar
        name={them?.player.display_name ?? '?'}
        mascot={them?.player.mascot}
        size={36}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-chalk">vs {them?.player.display_name ?? 'Unknown'}</p>
        <p className="text-xs text-ash">
          {match.category} · {match.question_count} questions · {timeAgo(match.completed_at ?? match.started_at)}
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

/* --- Signed out ------------------------------------------------------------ */

function GuestHome() {
  return (
    <div className="flex flex-col gap-6 pb-4 sm:gap-8">
      <GuestHero />
      <Button as={Link} to="/play" variant="accent" size="full">
        Find a match
      </Button>
      <HowItWorks />
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
