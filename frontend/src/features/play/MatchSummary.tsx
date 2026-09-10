import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Handshake, LogOut, Repeat, Trophy } from 'lucide-react'
import { getMatch } from '../../lib/api/endpoints'
import { queryKeys } from '../../lib/query/queryClient'
import type { MatchCompletedMessage } from '../../lib/realtime'
import { Avatar } from '../../components/Avatar'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { StatusBadge } from '../../components/StatusBadge'
import { Loading } from '../../components/states'

/*
 * The end of a match.
 *
 * This is where the box score is fetched, and the timing is the point: `GET
 * /matches/{id}/` returns every question of the match, so during play it would
 * hand this client the board it has not been shown yet. The matchup is terminal
 * by the time this component mounts, so there is nothing left to leak — and
 * this is also the first moment the app can put a *name* to the opponent, since
 * nothing on the socket carries one.
 *
 * The fetch is therefore best-effort rather than load-bearing. The result
 * itself came over the socket and is already on screen; the names, the
 * category and the per-question review are an enrichment that arrives a beat
 * later. If it fails, the screen still says who won and by how much.
 */
export function MatchSummary({
  matchupId,
  completed,
  myPlayerId,
  categorySlug,
}: {
  matchupId: string
  completed: MatchCompletedMessage
  myPlayerId: string | null
  /** Where "Play again" goes back to. Known from the route the player came in
   *  on, so it doesn't have to wait for the box score to resolve. */
  categorySlug: string | null
}) {
  const boxScore = useQuery({
    queryKey: queryKeys.matches.detail(matchupId),
    queryFn: () => getMatch(matchupId),
    // The match just ended; whatever is cached from a previous visit is stale
    // by definition, and the fresh copy is what carries the final state.
    staleTime: 0,
  })

  const sides = boxScore.data?.players ?? []
  const nameFor = (playerId: string) =>
    sides.find((side) => side.player.id === playerId)?.player.display_name ?? null
  const avatarFor = (playerId: string) =>
    sides.find((side) => side.player.id === playerId)?.player.avatar_url ?? null

  const myScore = myPlayerId ? (completed.scores[myPlayerId] ?? 0) : 0
  const opponentId = Object.keys(completed.scores).find((id) => id !== myPlayerId) ?? null
  const theirScore = opponentId ? (completed.scores[opponentId] ?? 0) : 0

  // A null winner is the double tie the server leaves unbroken — level on
  // points *and* on total answer time. Rare, and a real outcome rather than an
  // error, so it gets its own word instead of being rounded to a loss.
  const drew = completed.winner_player_id === null
  const won = !drew && completed.winner_player_id === myPlayerId

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-5 motion-safe:animate-rise-in">
      <Banner won={won} drew={drew} abandoned={completed.outcome === 'abandoned'} />

      <Card className="flex items-stretch gap-3 p-4">
        <Finalist
          name={(myPlayerId && nameFor(myPlayerId)) ?? 'You'}
          seed={myPlayerId ?? 'you'}
          avatarUrl={myPlayerId ? avatarFor(myPlayerId) : null}
          score={myScore}
          winner={won}
          accent="court"
        />
        <div className="flex shrink-0 items-center">
          <span className="font-display text-sm font-bold uppercase tracking-[0.2em] text-ash">
            vs
          </span>
        </div>
        <Finalist
          name={(opponentId && nameFor(opponentId)) ?? 'Rival'}
          seed={opponentId ?? 'rival'}
          avatarUrl={opponentId ? avatarFor(opponentId) : null}
          score={theirScore}
          winner={!drew && !won}
          accent="rival"
        />
      </Card>

      {/* The rating change is deliberately not shown here. `match.completed`
          doesn't carry one, and the ladder moves inside the same transaction
          that ended the match — so the honest place to see the new number is
          the profile, which reads it rather than guessing at a delta. */}

      <div className="flex flex-col gap-2 sm:flex-row">
        {categorySlug && (
          <Button as={Link} to={`/play/${categorySlug}`} size="full" variant="primary">
            <Repeat size={18} aria-hidden />
            Play again
          </Button>
        )}
        <Button as={Link} to={`/matches/${matchupId}`} size="full" variant="secondary">
          Question by question
        </Button>
      </div>

      {boxScore.isLoading && <Loading label="Loading the box score…" />}
    </div>
  )
}

function Banner({
  won,
  drew,
  abandoned,
}: {
  won: boolean
  drew: boolean
  abandoned: boolean
}) {
  const { tone, title, sub } = drew
    ? {
        tone: 'from-court/30',
        title: 'Dead heat',
        sub: 'Level on points and level on the clock — nobody edged it.',
      }
    : won
      ? {
          tone: 'from-gold/30',
          title: 'You win',
          sub: abandoned ? 'Your rival left the match.' : 'Rating and badges are on their way.',
        }
      : {
          tone: 'from-white/10',
          title: 'You lose',
          sub: abandoned ? 'You left the match.' : 'Straight back in — the pool is open.',
        }

  return (
    <div
      className={`relative overflow-hidden rounded-card border border-white/8 bg-gradient-to-b ${tone} to-transparent p-6 text-center`}
    >
      {/* The winner's banner gets a sweeping highlight; a loss does not. A
          celebration animation on a defeat reads as being taunted. */}
      {won && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-0 -left-1/3 w-1/3 bg-gradient-to-r from-transparent via-white/12 to-transparent motion-safe:animate-shimmer"
        />
      )}
      {drew ? (
        <Handshake size={34} className="mx-auto mb-2 text-court" aria-hidden />
      ) : won ? (
        <Trophy size={34} className="mx-auto mb-2 text-gold" aria-hidden />
      ) : (
        <LogOut size={34} className="mx-auto mb-2 text-idle" aria-hidden />
      )}
      <h1 className="font-display text-3xl font-bold uppercase tracking-tight text-chalk">
        {title}
      </h1>
      <p className="mt-1 text-sm text-ash">{sub}</p>
      {abandoned && (
        // Worth naming, because it moved the ladder exactly as a played-out
        // match would — an abandoned win is not a lesser win, and a player who
        // wasn't told would assume it didn't count.
        <StatusBadge tone="warn" className="mt-3">
          Abandoned · still ranked
        </StatusBadge>
      )}
    </div>
  )
}

function Finalist({
  name,
  seed,
  avatarUrl,
  score,
  winner,
  accent,
}: {
  name: string
  seed: string
  avatarUrl: string | null
  score: number
  winner: boolean
  accent: 'court' | 'rival'
}) {
  return (
    <div
      className={`flex min-w-0 flex-1 flex-col items-center gap-2 rounded-tile border p-3 ${
        winner
          ? 'border-gold/50 bg-gold/8'
          : accent === 'court'
            ? 'border-court/30'
            : 'border-rival/30'
      }`}
    >
      <Avatar name={name} seed={seed} avatarUrl={avatarUrl} size={48} ring={winner} />
      <span className="w-full truncate text-center text-sm font-medium text-chalk">{name}</span>
      <span
        className={`nums font-display text-3xl font-bold leading-none ${
          winner ? 'text-gold' : 'text-ash'
        }`}
      >
        {score}
      </span>
    </div>
  )
}
