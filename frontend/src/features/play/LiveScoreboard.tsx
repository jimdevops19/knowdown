import { Check, WifiOff } from 'lucide-react'
import { Avatar } from '../../components/Avatar'
import type { MatchupState } from '../../lib/realtime'

/*
 * The two sides of a live match, above the board.
 *
 * ── The opponent's name ───────────────────────────────────────────────────────
 * Fetched by the caller from `GET /matches/{id}/participants/` — name and
 * picture only, nothing the socket wouldn't already be fine with saying. Until
 * that request resolves (a beat, at the start of a match), `opponentName`
 * arrives here as the literal fallback "Rival", coloured by a hue derived from
 * their id (`Avatar`'s `seed`) so there's a specific someone to look at rather
 * than a blank even in that window.
 *
 * The scoreboard shows *points*, not questions won — points are what the ladder
 * moves on, and they carry speed as well as correctness, so a player who is
 * level on answers and behind on the clock can see that they are behind.
 */
export function LiveScoreboard({
  state,
  myPlayerId,
  myName,
  myAvatarUrl,
  opponentName,
  opponentAvatarUrl,
}: {
  state: MatchupState
  myPlayerId: string | null
  myName: string
  myAvatarUrl: string | null
  opponentName: string
  opponentAvatarUrl: string | null
}) {
  const opponentId = findOpponentId(state, myPlayerId)
  const myScore = myPlayerId ? state.scores[myPlayerId] : undefined
  const theirScore = opponentId ? state.scores[opponentId] : undefined

  return (
    <div className="flex items-stretch gap-2">
      <Side
        name={myName}
        seed={myPlayerId ?? myName}
        avatarUrl={myAvatarUrl}
        score={myScore}
        known={state.scoresComplete}
        accent="court"
        answered={state.mySubmission !== null}
        align="left"
      />

      <div className="flex shrink-0 flex-col items-center justify-center px-1">
        <span className="font-display text-xs font-bold uppercase tracking-[0.2em] text-ash">
          vs
        </span>
      </div>

      <Side
        name={opponentName}
        // Seeded on the opponent's id so their colour is stable across the
        // whole match even in the brief window before the name resolves.
        seed={opponentId ?? 'rival'}
        avatarUrl={opponentAvatarUrl}
        score={theirScore}
        known={state.scoresComplete}
        accent="rival"
        answered={state.opponentAnswered}
        away={state.opponentAway}
        align="right"
      />
    </div>
  )
}

function Side({
  name,
  seed,
  avatarUrl,
  score,
  known,
  accent,
  answered,
  away = false,
  align,
}: {
  name: string
  seed: string
  avatarUrl: string | null
  score: number | undefined
  known: boolean
  accent: 'court' | 'rival'
  answered: boolean
  away?: boolean
  align: 'left' | 'right'
}) {
  /*
   * Each side is marked on its *outer* edge — a 3px bar of its own colour on
   * the left for you, on the right for them, mirroring outward from the centre
   * the way a scoreboard flanks the score.
   *
   * The two colours are orange and azure, and that pairing is a legibility
   * decision before an aesthetic one: this is the single most important
   * distinction in the app, read on a phone at arm's length with seconds on the
   * clock, and orange-against-blue is the one opposition that survives both
   * common forms of colour blindness — as well as being the oldest pair of kits
   * in sport. The bars mean the sides stay told apart even where the colour
   * doesn't land at all.
   */
  const edge =
    accent === 'court'
      ? 'border-l-4 border-l-court'
      : 'border-r-4 border-r-rival'
  const text = accent === 'court' ? 'text-court' : 'text-rival'

  return (
    <div
      className={`flex min-w-0 flex-1 items-center gap-2.5 rounded-card border border-chalk/8 bg-panel px-3 py-2.5 ${edge} ${
        align === 'right' ? 'flex-row-reverse text-right' : ''
      } ${away ? 'opacity-60' : ''}`}
    >
      <Avatar name={name} seed={seed} avatarUrl={avatarUrl} size={36} ring={answered} />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="flex items-center gap-1.5 truncate text-sm font-medium text-chalk">
          {away && <WifiOff size={13} className="shrink-0 text-rival" aria-hidden />}
          <span className="truncate">{name}</span>
        </span>
        {/* The score, in widened display digits — the one number on the screen
            that is meant to be seen from further away than it is read. */}
        <span
          className={`nums font-display text-2xl font-bold [font-stretch:var(--display-wide)] leading-none ${text}`}
        >
          {/* A dash rather than a number this client cannot vouch for. A
              reconnect resumes at the question in progress and is told nothing
              about the ones already played, so the running total would be
              quietly short — and a scoreboard that is quietly wrong is worse
              than one that admits it doesn't know. The real figure arrives with
              `match.completed`. */}
          {known ? (score ?? 0) : '—'}
        </span>
      </div>
      {/* "They locked in" — who, never what. The opponent's verdict is not
          published while this player's clock is still running, and this badge
          is the whole of what may be said about it. */}
      {answered && (
        <span
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-[4px] ${
            accent === 'court' ? 'bg-court/25 text-court' : 'bg-rival/25 text-rival'
          }`}
          title="Locked in"
        >
          <Check size={13} aria-hidden />
        </span>
      )}
    </div>
  )
}

/**
 * Which id in the score line isn't mine.
 *
 * Read off the scores rather than tracked separately: the first
 * `question.result` names both players, so the opponent is known from the end
 * of question one onward. Before that there is nothing to show but "Rival"
 * anyway, which is what the null falls back to.
 */
function findOpponentId(state: MatchupState, myPlayerId: string | null): string | null {
  const ids = Object.keys(state.scores)
  return ids.find((id) => id !== myPlayerId) ?? null
}
