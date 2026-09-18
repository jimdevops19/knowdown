import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Flag, WifiOff } from 'lucide-react'
import { useAuth } from '../features/auth/useAuth'
import { useMatchup, UNAVAILABLE_REASONS } from '../lib/realtime'
import { useQuestionClock } from '../hooks/useQuestionClock'
import { getMatchParticipants } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { Countdown } from '../features/play/Countdown'
import { LiveScoreboard } from '../features/play/LiveScoreboard'
import { QuestionBoard } from '../features/play/QuestionBoard'
import { QuestionVerdict } from '../features/play/QuestionVerdict'
import { MatchSummary } from '../features/play/MatchSummary'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { StatusBadge } from '../components/StatusBadge'
import { ConfirmDialog } from '../components/ConfirmDialog'

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
 * ── The opponent's name ──────────────────────────────────────────────────────
 * The socket carries player ids and no names. `GET /matches/{id}/participants/`
 * resolves them — name and picture only, nothing about the score — so it is
 * safe to call the moment this page mounts, unlike `GET /matches/{id}/` (the
 * box score), which stays refused until the match ends because it also carries
 * every question and the opponent's live submissions. Until that fetch
 * resolves, the opponent is still "Rival" with a colour derived from their id.
 *
 * ── The clock decides nothing ───────────────────────────────────────────────
 * `useQuestionClock` draws the server's clock for this question — however long
 * the server said it is — but it does not enforce it.
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
  const participants = useQuery({
    queryKey: queryKeys.matches.participants(id),
    queryFn: () => getMatchParticipants(id),
    enabled: Boolean(id),
    // The two sides of a matchup never change once it exists, so there is
    // nothing here a background refetch would ever find different.
    staleTime: Infinity,
  })
  const opponent =
    participants.data?.find((row) => row.player.id !== playerId)?.player ?? null
  const [confirmingForfeit, setConfirmingForfeit] = useState(false)
  const onQuestion = match.phase === 'question'
  const clock = useQuestionClock(
    onQuestion ? (match.current?.seenAt ?? null) : null,
    onQuestion ? (match.current?.timeLimitMs ?? null) : null,
  )

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

  // When the server closes this question, as one stable instant. Derived from
  // the same two numbers the countdown is drawn from, so a board acting on it
  // and the bar the player is watching cannot disagree — and stable, so a board
  // holding a timer against it is not re-arming it sixty times a second.
  const deadlineAt =
    onQuestion && match.current ? match.current.seenAt + match.current.timeLimitMs : null

  // The read delay's whole purpose: the player has nothing to look at but the
  // question until it has elapsed, so the options and the running clock stay
  // out of the DOM rather than sitting there inert for those three seconds.
  const revealOptions = clock.started

  const opponentThinking =
    match.phase === 'question' &&
    match.mySubmission !== null &&
    !match.opponentAnswered &&
    !match.opponentAway

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
        <div className="flex items-center gap-3">
          {match.phase === 'connecting' && (
            <span className="flex items-center gap-1.5 text-xs text-gold">
              <WifiOff size={13} aria-hidden />
              Reconnecting…
            </span>
          )}
          {/* Tucked into the header rather than near the board: a forfeit is
              reached for between questions, never in the middle of tapping an
              answer, so it lives beside the other status chrome instead of
              competing with the tiles for thumb space. */}
          {match.canForfeit && (
            <button
              type="button"
              onClick={() => setConfirmingForfeit(true)}
              aria-label="Forfeit match"
              className="flex items-center gap-1 rounded-btn px-2 py-1 text-xs text-ash transition-colors hover:bg-wrong/10 hover:text-wrong"
            >
              <Flag size={13} aria-hidden />
              Forfeit
            </button>
          )}
        </div>
      </header>

      <div className="shrink-0">
        <LiveScoreboard
          state={match}
          myPlayerId={playerId}
          myName={user?.player_name ?? 'You'}
          myAvatarUrl={user?.player_avatar_url ?? null}
          opponentName={opponent?.display_name ?? 'Rival'}
          opponentAvatarUrl={opponent?.avatar_url ?? null}
        />
      </div>

      {/* Held back until the read delay elapses, so the timer appears at the
          same moment as the options it is timing rather than sitting full and
          motionless while there is nothing yet to answer. */}
      {revealOptions && (
        <div className="shrink-0 motion-safe:animate-fade-in">
          <Countdown clock={clock} />
        </div>
      )}

      {opponentThinking && (
        <p className="flex shrink-0 items-center justify-center gap-2 text-center text-sm text-ash motion-safe:animate-fade-in">
          <span className="flex items-center gap-1" aria-hidden>
            <span className="h-1.5 w-1.5 rounded-full bg-rival motion-safe:animate-live-pulse [animation-delay:0ms]" />
            <span className="h-1.5 w-1.5 rounded-full bg-rival motion-safe:animate-live-pulse [animation-delay:0.2s]" />
            <span className="h-1.5 w-1.5 rounded-full bg-rival motion-safe:animate-live-pulse [animation-delay:0.4s]" />
          </span>
          Opponent still thinking…
        </p>
      )}

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
            hints={match.hints}
            submission={match.mySubmission}
            verdict={verdictFor(match, playerId)}
            locked={locked}
            deadlineAt={deadlineAt}
            onAnswer={match.answer}
            revealOptions={revealOptions}
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
          <QuestionVerdict
            results={match.results}
            myPlayerId={playerId}
            opponentName={opponent?.display_name ?? 'Rival'}
          />
        </div>
      )}

      <ConfirmDialog
        open={confirmingForfeit}
        title="Forfeit this match?"
        description="You'll lose immediately and your rival is awarded the win. This can't be undone."
        confirmLabel="Forfeit"
        cancelLabel="Keep playing"
        onCancel={() => setConfirmingForfeit(false)}
        onConfirm={() => {
          setConfirmingForfeit(false)
          match.forfeit()
        }}
      />
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
