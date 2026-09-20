import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Eye, Handshake, LayoutGrid, LogOut, Repeat, Trophy } from 'lucide-react'
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
  roomSlug,
}: {
  matchupId: string
  completed: MatchCompletedMessage
  myPlayerId: string | null
  /** The room the player came in on, off the route. A hint, not the answer:
   *  it is there immediately, so "Play again" is live before the box score
   *  resolves, but the box score's own `room` is what the match was actually
   *  played in and wins where the two disagree (see below). */
  roomSlug: string | null
}) {
  const boxScore = useQuery({
    queryKey: queryKeys.matches.detail(matchupId),
    queryFn: () => getMatch(matchupId),
    // The match just ended; whatever is cached from a previous visit is stale
    // by definition, and the fresh copy is what carries the final state.
    staleTime: 0,
  })

  /*
   * Which room "Play again" re-enters.
   *
   * The box score is the record of what was *played*, so it is the one that
   * decides — `?from=` is whatever the last screen put in the URL, and it is
   * missing entirely for a player who reached this match by link or by
   * reconnecting. Reading the room off the match is what makes the button mean
   * "these exact settings again" rather than "whichever room the URL mentioned".
   *
   * The route's slug is still worth keeping as the stand-in until that fetch
   * lands: it is right in the ordinary case and it is there a beat earlier.
   * Null from both — an old match with no room, or a box score that failed —
   * leaves only "Back to rooms", which is the honest offer when the app cannot
   * say what was played.
   */
  const playAgainRoom = boxScore.data?.room ?? roomSlug

  const sides = boxScore.data?.players ?? []
  const nameFor = (playerId: string) =>
    sides.find((side) => side.player.id === playerId)?.player.display_name ?? null
  const avatarFor = (playerId: string) =>
    sides.find((side) => side.player.id === playerId)?.player.avatar_url ?? null
  const mascotFor = (playerId: string) =>
    sides.find((side) => side.player.id === playerId)?.player.mascot ?? null

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
      <Banner
        won={won}
        drew={drew}
        abandoned={completed.outcome === 'abandoned'}
        // Defaults to ranked while the box score is in flight: the ordinary
        // match is ranked, and flashing "Unrated" for a beat on a game that
        // counted is the worse of the two wrong answers.
        ranked={boxScore.data?.is_ranked ?? true}
      />

      <Card className="flex items-stretch gap-3 p-4">
        <Finalist
          name={(myPlayerId && nameFor(myPlayerId)) ?? 'You'}
          seed={myPlayerId ?? 'you'}
          avatarUrl={myPlayerId ? avatarFor(myPlayerId) : null}
          mascot={myPlayerId ? mascotFor(myPlayerId) : null}
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
          mascot={opponentId ? mascotFor(opponentId) : null}
          score={theirScore}
          winner={!drew && !won}
          accent="rival"
        />
      </Card>

      {/* The rating change is deliberately not shown here. `match.completed`
          doesn't carry one, and the ladder moves inside the same transaction
          that ended the match — so the honest place to see the new number is
          the profile, which reads it rather than guessing at a delta. */}

      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-2 sm:flex-row">
          {playAgainRoom && (
            <Button
              as={Link}
              to={`/play/${encodeURIComponent(playAgainRoom)}`}
              size="full"
              variant="primary"
            >
              <Repeat size={18} aria-hidden />
              Play again
            </Button>
          )}
          <Button as={Link} to={`/matches/${matchupId}`} size="full" variant="secondary">
            <Eye size={18} aria-hidden />
            See what you got right
          </Button>
        </div>
        {/* The other half of "again": the same room, or a different one. Ghost
            rather than a third solid button — it is the way out of this loop,
            not a competitor to the two verbs above. */}
        <Button as={Link} to="/play" size="full" variant="ghost">
          <LayoutGrid size={18} aria-hidden />
          Back to rooms
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
  ranked,
}: {
  won: boolean
  drew: boolean
  abandoned: boolean
  ranked: boolean
}) {
  /*
   * The result, and the one screen in the app allowed to be theatrical.
   *
   * ── Why a win is a different *kind* of object, not a different colour ──────
   * This has now been wrong twice in the same way. It began as a panel with a
   * 3px band of the result colour along its top edge — a broadcast result
   * graphic, which reports an outcome to somebody who wasn't playing, on a
   * screen only ever read by the person who just won. The fix was to flood the
   * whole panel in mint, and that traded one wrong register for another: a
   * full-bleed field of a single flat colour with dark text on it is the shape
   * of a *confirmation* — payment received, settings saved — and it read as one.
   *
   * Flat colour is not what makes a victory screen. Light is. So the panel goes
   * back to the app's darkest ink and the celebration happens *on* it: rays
   * turning slowly out from behind a struck gold medal, the medal itself
   * dropping in and settling, the result in gold display caps a size larger than
   * any other headline in the app. Everything luminous, nothing flat.
   *
   * Gold rather than mint, which is the reverse of the earlier call. The
   * argument for mint was that gold means *rank* elsewhere in the app — true,
   * but mint means something far more frequent: it is every right answer, and
   * the ring on every correct tile. Spending it a fourth time on the match
   * result made the biggest moment in the game look like one more question gone
   * well. Gold is the only bright colour here that a player has not already seen
   * ten times in the last two minutes.
   *
   * It all arrives on the reward motion tier (index.css) — a rise that takes
   * 0.85s and a medal that drops and bounces, both several times slower than
   * anything permitted during play, because the whole job of this half-second is
   * to feel like winning something.
   *
   * ── And why a loss is still quiet ─────────────────────────────────────────
   * A loss and a draw keep the plate and the struck band. Turning the reward
   * treatment symmetrical would mean rays and a medal on every second game,
   * which is not "honest about the result", it is being taunted for losing.
   */
  const { tone, title, sub } = drew
    ? {
        tone: 'border-2 border-chalk/14 border-t-[3px] border-t-court bg-panel shadow-card',
        title: 'Dead heat',
        sub: 'Level on points and level on the clock — nobody edged it.',
      }
    : won
      ? {
          tone: 'border-2 border-gold/45 bg-void shadow-lip-gold',
          title: 'You win',
          // "Rating … on their way" is a promise, so it is only made when one
          // is coming. An unranked win still earns badges; it just moves no
          // number, and the badge below says why.
          sub: abandoned
            ? 'Your rival left the match.'
            : ranked
              ? 'Rating and badges are on their way.'
              : 'Badges are on their way.',
        }
      : {
          tone: 'border-2 border-chalk/14 border-t-[3px] border-t-idle bg-panel shadow-card',
          title: 'You lose',
          sub: abandoned ? 'You left the match.' : 'Straight back in — the pool is open.',
        }

  return (
    <div
      className={`relative overflow-hidden rounded-card px-6 py-8 text-center ${tone} ${
        won ? 'motion-safe:animate-reward-rise' : ''
      }`}
    >
      {/* The rays. A victory screen in a game is lit from behind the trophy,
          and that is the whole difference between this and a banner that
          announces a result: the light is the celebration, and it costs no
          legibility because it lives under the type rather than in it.

          Masked to a circle centred on the trophy so it reads as a burst from
          one point rather than as a striped background, and turning slowly
          enough (24s) to be felt rather than watched. */}
      {won && (
        <>
          {/* The warm ground the rays are read against. Gold laid straight onto
              this navy at low alpha mixes to olive — the spokes came out the
              colour of old moss. The glow sits underneath and warms the whole
              centre, so the same gold reads as light rather than as a tint. */}
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                'radial-gradient(circle at 50% 30%, rgba(255,160,46,0.22), transparent 62%)',
            }}
          />
          <span
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-[30%] aspect-square w-[160%] -translate-x-1/2 -translate-y-1/2 motion-safe:animate-[spin_24s_linear_infinite]"
            style={{
              background:
                'repeating-conic-gradient(from 0deg, rgba(255,200,70,0.13) 0deg 7deg, transparent 7deg 22deg)',
              maskImage: 'radial-gradient(circle, #000 0%, transparent 62%)',
              WebkitMaskImage: 'radial-gradient(circle, #000 0%, transparent 62%)',
            }}
          />
        </>
      )}
      {drew ? (
        <Handshake size={34} className="mx-auto mb-2 text-court" aria-hidden />
      ) : won ? (
        // The trophy is a struck medal, not an icon in a paragraph: a solid
        // gold disc with the cup cut out of it in the app's dark ink, dropped
        // in on the reward tier so it lands and settles.
        //
        // Gold, and not the mint this banner used to be painted in. A
        // full-bleed mint plate is the shape of a *confirmation* — payment
        // received, settings saved — and it was reading as one. Mint is also
        // already spoken for three times over on the way to this screen: it is
        // every right answer and the verdict ring on every tile. Spending it
        // again on the match result made the biggest moment in the app look
        // like one more correct answer.
        <span className="relative mx-auto mb-3 flex h-20 w-20 items-center justify-center rounded-full bg-gold text-void shadow-lip-gold motion-safe:animate-trophy-land">
          <Trophy size={40} strokeWidth={2.5} aria-hidden />
        </span>
      ) : (
        <LogOut size={34} className="mx-auto mb-2 text-idle" aria-hidden />
      )}
      <h1
        className={`relative text-headline ${won ? 'text-5xl text-gold' : 'text-4xl text-chalk'}`}
      >
        {title}
      </h1>
      <p className="relative mt-1 text-sm text-ash">{sub}</p>
      {/* One badge, because the two things it can say are about the same
          question — did this count? — and stacking them would make the
          screen argue with itself. Unranked wins: "abandoned but it still
          counted" is meaningless for a match that never counted. */}
      {!ranked ? (
        // The only place a player finds out for certain. A room that mixes
        // categories cannot move a ladder (`Room.is_rated`), and the lobby
        // says so up front, but a match reached by link or by reconnecting
        // never passed through the lobby.
        <StatusBadge tone="neutral" className="relative mt-3">
          Unrated · no rating change
        </StatusBadge>
      ) : (
        abandoned && (
          // Worth naming, because it moved the ladder exactly as a played-out
          // match would — an abandoned win is not a lesser win, and a player
          // who wasn't told would assume it didn't count.
          <StatusBadge tone="warn" className="relative mt-3">
            Abandoned · still ranked
          </StatusBadge>
        )
      )}
    </div>
  )
}

function Finalist({
  name,
  seed,
  avatarUrl,
  mascot,
  score,
  winner,
  accent,
}: {
  name: string
  seed: string
  avatarUrl: string | null
  mascot: string | null
  score: number
  winner: boolean
  accent: 'court' | 'rival'
}) {
  return (
    // The winning side is filled, the losing side is outlined. Same move as the
    // answer tiles: the state is the surface, not a stripe on the edge of it —
    // which is what lets the final score be read from the two cells' *shapes*
    // before either number is.
    <div
      className={`flex min-w-0 flex-1 flex-col items-center gap-2 rounded-tile border-2 p-3 ${
        winner
          ? 'border-transparent bg-gold text-void shadow-lip-gold'
          : accent === 'court'
            ? 'border-court/40'
            : 'border-rival/40'
      }`}
    >
      <Avatar
        name={name}
        seed={seed}
        avatarUrl={avatarUrl}
        mascot={mascot}
        size={48}
        ring={winner}
      />
      <span
        className={`w-full truncate text-center text-sm font-semibold ${
          winner ? '' : 'text-chalk'
        }`}
      >
        {name}
      </span>
      {/* The winner's number lands on the reward tier — it overshoots and
          settles, so the score *arrives* rather than simply being present. */}
      <span
        className={`nums font-display text-3xl font-bold leading-none ${
          winner ? 'motion-safe:animate-reward-pop' : 'text-ash'
        }`}
      >
        {score}
      </span>
    </div>
  )
}
