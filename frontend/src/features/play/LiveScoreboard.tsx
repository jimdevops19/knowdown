import { Check, WifiOff } from 'lucide-react'
import { Avatar } from '../../components/Avatar'
import type { MatchupState } from '../../lib/realtime'

/*
 * The two sides of a live match, above the board.
 *
 * ── Why the opponent has no name ─────────────────────────────────────────────
 * The socket never sends one. `player.answered` carries a player id,
 * `match.completed` carries scores keyed by player id, and there is no
 * id-to-name lookup in the public API — profiles are fetched by display name.
 * The one endpoint that *would* answer it, `GET /matches/{id}/`, returns the
 * full box score including every question of the match, which mid-game is the
 * rest of the board; asking for it during a live match would hand this client
 * the questions it has not been shown yet. (See `MatchPage` — that request is
 * deliberately deferred until the match is over.)
 *
 * So during play the opponent is "Rival", coloured by a hue derived from their
 * id (`Avatar`'s `seed`), which is stable for the whole match. It reads as a
 * specific someone rather than a blank, and the name arrives on the summary
 * screen a few seconds later. That is the honest trade, and it is worth
 * preferring over the alternative: there is nothing to show at all if the only
 * way to get a name is to also get the answers.
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
}: {
  state: MatchupState
  myPlayerId: string | null
  myName: string
  myAvatarUrl: string | null
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
        name="Rival"
        // Seeded on the opponent's id so their colour is stable across the whole
        // match even though their name isn't known. Falls back to the literal
        // string only in the window before they have answered anything.
        seed={opponentId ?? 'rival'}
        avatarUrl={null}
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
  const border = accent === 'court' ? 'border-court/40' : 'border-rival/40'
  const text = accent === 'court' ? 'text-court' : 'text-rival'

  return (
    <div
      className={`flex min-w-0 flex-1 items-center gap-2.5 rounded-card border bg-panel/70 px-3 py-2.5 backdrop-blur-md ${border} ${
        align === 'right' ? 'flex-row-reverse text-right' : ''
      } ${away ? 'opacity-60' : ''}`}
    >
      <Avatar name={name} seed={seed} avatarUrl={avatarUrl} size={36} ring={answered} />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="flex items-center gap-1.5 truncate text-sm font-medium text-chalk">
          {away && <WifiOff size={13} className="shrink-0 text-rival" aria-hidden />}
          <span className="truncate">{name}</span>
        </span>
        <span className={`nums font-display text-xl font-bold leading-none ${text}`}>
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
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
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
