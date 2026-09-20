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
 * ── No score during play ─────────────────────────────────────────────────────
 * The running totals are *concealed* until the match is over. Points carry
 * speed as well as correctness, so a mid-match total is a number a player would
 * play differently against — chasing a deficit that a fast wrong answer only
 * deepens — and watching it tick is attention spent off the question. Each side
 * keeps its place in the layout as three dots, and the real figures arrive all
 * at once on the summary screen (`MatchSummary`, off `match.completed`).
 *
 * What *is* still said here is whether each side has locked in — who, never
 * what — which is the only thing about the opponent that may be published while
 * this player's clock is running.
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

  return (
    <div className="flex items-stretch gap-2">
      <Side
        name={myName}
        seed={myPlayerId ?? myName}
        avatarUrl={myAvatarUrl}
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
  accent,
  answered,
  away = false,
  align,
}: {
  name: string
  seed: string
  avatarUrl: string | null
  accent: 'court' | 'rival'
  answered: boolean
  away?: boolean
  align: 'left' | 'right'
}) {
  /*
   * Each side is outlined in its own colour, two pixels the whole way round.
   *
   * This used to be a 4px bar on the *outer* edge only — left for you, right for
   * them — mirroring outward the way a scoreboard flanks a score. That was a
   * nice idea at a 10px corner radius and it broke at 19px: a thick border on
   * one side of a generously rounded box doesn't read as a bar, it reads as a
   * crescent hooked around the corner, because the border has to turn the radius
   * with nothing on the adjacent side to turn into. The outward mirroring is not
   * worth a rendering artefact on the screen people stare at hardest.
   *
   * A full outline says the same thing and says it louder — each side is now a
   * discretely kitted object rather than a panel with a stripe. The two colours
   * are unchanged and still carry the real weight: orange against azure is a
   * legibility decision before an aesthetic one, the one opposition that
   * survives both common forms of colour blindness, and the oldest pair of kits
   * in sport. Position (yours left, theirs right) and the avatar carry the
   * distinction wherever colour doesn't land at all.
   */
  const edge = accent === 'court' ? 'border-court' : 'border-rival'
  const text = accent === 'court' ? 'text-court' : 'text-rival'

  return (
    <div
      className={`flex min-w-0 flex-1 items-center gap-2.5 rounded-card border-2 bg-panel px-3 py-2.5 shadow-card ${edge} ${
        align === 'right' ? 'flex-row-reverse text-right' : ''
      } ${away ? 'opacity-60' : ''}`}
    >
      <Avatar name={name} seed={seed} avatarUrl={avatarUrl} size={36} ring={answered} />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="flex items-center gap-1.5 truncate text-sm font-medium text-chalk">
          {away && <WifiOff size={13} className="shrink-0 text-rival" aria-hidden />}
          <span className="truncate">{name}</span>
        </span>
        {/* Where the score goes, holding its place at the same size and colour
            so the reveal at the end lands in a shape the player already knows.
            Dots rather than a dash: a dash reads as "nothing yet", and there
            very much is something — it is simply not being shown. */}
        <span
          role="img"
          aria-label="Score hidden until the end of the match"
          title="Scores are revealed at the end of the match"
          className={`font-display text-2xl font-bold leading-none tracking-[0.1em] opacity-50 ${text}`}
        >
          •••
        </span>
      </div>
      {/* "They locked in" — who, never what. The opponent's verdict is not
          published while this player's clock is still running, and this badge
          is the whole of what may be said about it. */}
      {answered && (
        <span
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-pill ${
            accent === 'court' ? 'bg-court text-void' : 'bg-rival text-void'
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
