import { useEffect } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { WifiOff } from 'lucide-react'
import { useAuth } from '../features/auth/useAuth'
import { useMatchup, UNAVAILABLE_REASONS } from '../lib/realtime'
import { useQuestionClock } from '../hooks/useQuestionClock'
import { queryKeys } from '../lib/query/queryClient'
import { Countdown } from '../features/play/Countdown'
import { LiveScoreboard } from '../features/play/LiveScoreboard'
import { QuestionBoard } from '../features/play/QuestionBoard'
import { QuestionVerdict } from '../features/play/QuestionVerdict'
import { MatchSummary } from '../features/play/MatchSummary'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { StatusBadge } from '../components/StatusBadge'

/*
 * `/match/:id` — the live game. The screen this whole app is for.
 *
 * ── The one layout rule ─────────────────────────────────────────────────────
 * **It does not scroll.** An answer tile below the fold is an answer the clock
 * runs out on, so the page caps itself at `--page-fit` (index.css: the viewport
 * minus the shell's chrome) and lays out as a three-part column — scoreboard,
 * board, verdict — with only the *board* allowed to give ground. Every other
 * screen in the app scrolls normally; this one is the exception, and it is the
 * reason `--page-fit` exists.
 *
 * ── What is not on this screen, and why ─────────────────────────────────────
 * The opponent's name. The socket carries player ids and no names, and the one
 * endpoint that would resolve them — `GET /matches/{id}/` — returns the whole
 * box score, meaning every question of the match, including the ones not yet
 * asked. Fetching it mid-game would hand this client the rest of the board.
 * So the roster is fetched *after* the match ends (see `MatchSummary`), and
 * during play the opponent is "Rival" with a colour derived from their id.
 *
 * ── The clock decides nothing ───────────────────────────────────────────────
 * `useQuestionClock` draws the server's ten seconds; it does not enforce them.
 * When it hits zero the board stops taking taps — that's all — and the question
 * genuinely closes when a `question.result` arrives. The two are within a round
 * trip of each other, and the gap belongs to the server.
 */
export function MatchPage() {
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  const { user, playerId } = useAuth()
  const queryClient = useQueryClient()

  const match = useMatchup(id || null, playerId)
  const clock = useQuestionClock(match.phase === 'question' ? (match.current?.seenAt ?? null) : null)

  // The match that just ended is a different document from the one any cached
  // box score holds, and the history list has a new row in it. Invalidate on
  // the transition rather than on every render of the completed state.
  useEffect(() => {
    if (match.phase !== 'completed') return
    void queryClient.invalidateQueries({ queryKey: queryKeys.matches.detail(id) })
    void queryClient.invalidateQueries({ queryKey: ['matches', 'mine'] })
    void queryClient.invalidateQueries({ queryKey: ['rankings'] })
  }, [match.phase, id, queryClient])

  if (match.phase === 'unavailable') {
    return (
      <Card className="mx-auto flex max-w-sm flex-col items-center gap-4 p-8 text-center">
        <p className="text-ash">
          {UNAVAILABLE_REASONS[match.closeCode ?? -1] ?? 'This match is no longer available.'}
        </p>
        <Button as={Link} to="/" size="full" variant="secondary">
          Back home
        </Button>
      </Card>
    )
  }

  if (match.phase === 'completed' && match.completed) {
    return (
      <MatchSummary
        matchupId={id}
        completed={match.completed}
        myPlayerId={playerId}
        categorySlug={params.get('from')}
      />
    )
  }

  const locked = !match.canAnswer || clock.expired

  return (
    <div
      // The whole point of `--page-fit`: this column is exactly the height left
      // over once the shell has taken its share, so nothing below it exists to
      // scroll to. `min-h-0` on the board's row is what lets a long question
      // shrink inside it rather than pushing the verdict strip off the bottom.
      className="mx-auto flex w-full max-w-2xl flex-col gap-3"
      style={{ height: 'var(--page-fit)' }}
    >
      <header className="flex shrink-0 items-center justify-between gap-2">
        <StatusBadge tone="live">
          {/* No denominator: the match length (3, 5 or 7) is chosen per matchup
              and never crosses the socket, so "Question 3 of 5" is not
              something this client can honestly say. The count of pips it has
              seen is, and that is what is shown. */}
          Question {match.current?.order ?? 1}
        </StatusBadge>
        {match.phase === 'connecting' && (
          <span className="flex items-center gap-1.5 text-xs text-gold">
            <WifiOff size={13} aria-hidden />
            Reconnecting…
          </span>
        )}
      </header>

      <div className="shrink-0">
        <LiveScoreboard
          state={match}
          myPlayerId={playerId}
          myName={user?.player_name ?? 'You'}
          myAvatarUrl={user?.player_avatar_url ?? null}
        />
      </div>

      <div className="shrink-0">
        <Countdown clock={clock} />
      </div>

      {match.opponentAway && (
        <p className="shrink-0 rounded-tile border border-rival/40 bg-rival/10 px-3 py-2 text-center text-sm text-rival">
          {/* Deliberately vague about *when*. The server holds a grace period
              and then ends the match itself; a countdown here would be this
              client predicting an outcome it does not own, and would show a win
              that never came if the opponent reconnected on the last tick. */}
          Your rival dropped out. If they don't come back, the match is yours.
        </p>
      )}

      {/* `min-h-0` + `overflow-y-auto`: a matrix question on a small phone is
          the one board that can genuinely exceed the space, and when it does it
          scrolls *inside here* rather than growing the page. Everything else
          fits, and this container never scrolls for them. */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {match.current ? (
          <QuestionBoard
            question={match.current.question}
            submission={match.mySubmission}
            verdict={verdictFor(match, playerId)}
            locked={locked}
            onAnswer={match.answer}
          />
        ) : (
          <p className="py-10 text-center text-ash motion-safe:animate-pulse">
            Waiting for the first question…
          </p>
        )}
      </div>

      {match.error && (
        <p role="alert" className="shrink-0 text-center text-sm text-wrong">
          {match.error.message}
        </p>
      )}

      {match.phase === 'result' && match.results && (
        <div className="shrink-0">
          <QuestionVerdict results={match.results} myPlayerId={playerId} />
        </div>
      )}
    </div>
  )
}

/**
 * This player's verdict on the question showing, or null while it is still
 * open.
 *
 * Read out of the results by id rather than tracked separately, so there is one
 * source for it. A player with no entry — the clock ran out on them — gets
 * `null` rather than `'wrong'`: they did not answer, so no tile on the board
 * should be painted as an answer that failed.
 */
function verdictFor(
  match: ReturnType<typeof useMatchup>,
  myPlayerId: string | null,
): 'correct' | 'wrong' | null {
  if (match.phase !== 'result' || !match.results) return null
  const mine = match.results.find((entry) => entry.player_id === myPlayerId)
  if (!mine) return null
  return mine.is_correct ? 'correct' : 'wrong'
}
