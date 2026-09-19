import { useCallback, useEffect, useMemo, useState } from 'react'
import { Dices, Eye, RotateCcw } from 'lucide-react'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { SectionHeading } from '../../components/SectionHeading'
import { Countdown } from '../play/Countdown'
import { QuestionBoard } from '../play/QuestionBoard'
import { useQuestionClock } from '../../hooks/useQuestionClock'
import { useInstantPassed } from '../../hooks/useInstantPassed'
import { QUESTION_READ_DELAY_MS } from '../../lib/config'
import type { AnswerKey, AnswerSubmission, TesterRehearsal, TesterVerdict } from '../../lib/api/types'
import { getTesterAnswerKeyFor, submitTesterAnswer } from './api'
import { AnswerKeyPanel } from './AnswerKeyPanel'
import { RehearsalVerdict } from './RehearsalVerdict'

/*
 * One question, played the way a match plays it.
 *
 * ## It is the real board, driven by the real clock
 *
 * `QuestionBoard` here is the *same component* `MatchPage` mounts, taking the
 * same `BoardProps`, rendering the same payload the socket would have carried —
 * and `useQuestionClock` is the same clock, counting down the same
 * `time_limit_ms` the server resolved for this question. Nothing about the
 * question is re-implemented for the tester, because a rehearsal that looked
 * right while a match looked wrong would be worse than no rehearsal: it would
 * be a screen that certifies broken questions.
 *
 * The staging is the match's staging, for the same reason. The options are held
 * back for `read_delay_ms` (`revealOptions={clock.started}`), the board locks
 * when the clock expires or an answer goes in, and a gradual-hints question's
 * clues arrive one at a time on the offsets the server scheduled them at —
 * replayed here against this client's clock, because there is no socket paying
 * them out. Waiting for a clue is what that question type *costs*, and a
 * rehearsal that dumped all five on screen at once would be rehearsing a
 * question nobody will ever be asked.
 *
 * ## The three things it does that a match cannot
 *
 * - **Deal again** (`seed`). The board order is a function of the seed, so this
 *   is the only honest way to check that an ordering question is not accidentally
 *   answerable from its authored order, or that a four-option board reads as
 *   well with the right answer last as with it first.
 * - **Run it again** (`runId`). A fresh clock, a fresh board, the same seed —
 *   for when the clock ran out while you were reading the code instead.
 *   Moving to a *different* question is not this: the page mounts one of these
 *   per `(type, id)` and keys it on the pair, so a new question is a new
 *   component with a new clock rather than this one being talked into
 *   forgetting the last one. Every piece of state here — the seed, the
 *   submission, the verdict, the clues shown so far — would otherwise need its
 *   own line in a reset effect, and the one that got left out would carry the
 *   previous question's answer onto the next question's board.
 * - **Just tell me** (the reveal button). Skips answering entirely; see
 *   `AnswerKeyPanel` for why that is a separate request rather than something
 *   the board arrives with.
 *
 * ## Why the verdict is a panel and not a strip
 *
 * `MatchPage` puts its verdict in a strip that the next question replaces in
 * seconds, and deliberately does not let it cover the board. Here nothing is
 * coming next: the answer key is the destination, the board above it is the
 * evidence, and both stay on screen together for as long as it takes to work
 * out why the question graded the way it did.
 */
export function Rehearsal({ rehearsal }: { rehearsal: TesterRehearsal }) {
  const [seed, setSeed] = useState(rehearsal.seed)
  const [runId, setRunId] = useState(0)
  // The clock's zero point, past the read delay — exactly what `useMatchup`'s
  // `seenAt` is in a live match. `useQuestionClock` treats a start in the
  // future as "not started yet", which is what draws the read delay for free.
  const [clockStart, setClockStart] = useState(() => Date.now() + rehearsal.read_delay_ms)

  const [submission, setSubmission] = useState<AnswerSubmission | null>(null)
  const [verdict, setVerdict] = useState<TesterVerdict | null>(null)
  const [peekedKey, setPeekedKey] = useState<AnswerKey | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [hints, setHints] = useState<string[]>([])

  const clock = useQuestionClock(clockStart, rehearsal.time_limit_ms)

  // The same boundary `MatchPage` draws, from the same two numbers: the task
  // screen owns the front of the delay, and the question is revealed
  // `QUESTION_READ_DELAY_MS` before the clock starts. A rehearsal shows it as a
  // strip rather than as the full-screen takeover a match uses — a maintainer
  // is inspecting this question, not playing it, and a black screen dropped
  // over the controls on every run would be in the way of the job.
  const taskBeatDone = useInstantPassed(
    rehearsal.board.pre_question_info ? clockStart - QUESTION_READ_DELAY_MS : null,
  )

  const restart = useCallback(
    (nextSeed?: string) => {
      if (nextSeed !== undefined) setSeed(nextSeed)
      setClockStart(Date.now() + rehearsal.read_delay_ms)
      setSubmission(null)
      setVerdict(null)
      setPeekedKey(null)
      setError(null)
      setHints([])
      // Bumped last: it is the remount key for the board, so every board starts
      // from nothing rather than from the previous attempt with its state
      // cleared — the same trick `QuestionBoard` uses per question in a match,
      // and for the same reason (a half-built grid must not survive into the
      // next run).
      setRunId((id) => id + 1)
    },
    [rehearsal.read_delay_ms],
  )

  /*
   * The hint schedule, replayed.
   *
   * One timeout per clue rather than an interval, so a late mount (or a tab
   * that was backgrounded) lands every clue that is already due immediately
   * instead of walking through them one interval at a time. Cleared on every
   * restart, or a second run would inherit the first run's pending timers and
   * reveal clues against the wrong clock.
   */
  useEffect(() => {
    if (rehearsal.hints.length === 0) return
    const timers = rehearsal.hints.map((hint) =>
      window.setTimeout(
        () => setHints((shown) => (shown.includes(hint.text) ? shown : [...shown, hint.text])),
        Math.max(0, clockStart + hint.offset_ms - Date.now()),
      ),
    )
    return () => timers.forEach(window.clearTimeout)
  }, [rehearsal.hints, clockStart, runId])

  const locked = submission !== null || clock.expired

  async function onAnswer(answer: AnswerSubmission) {
    // Set before the round trip, exactly as the live board does: a tapped tile
    // should read as taken rather than sitting inert and inviting a second tap.
    setSubmission(answer)
    setError(null)
    try {
      setVerdict(
        await submitTesterAnswer(
          rehearsal.type,
          rehearsal.id,
          answer,
          // Measured from the clock's zero point, which is where the server
          // would have measured it from. Negative is impossible for a real tap
          // (the board is not on screen yet) and clamped anyway.
          Math.max(0, Date.now() - clockStart),
        ),
      )
    } catch (failure) {
      // A refusal is a *result* here, not a crash: `malformed_answer` is a
      // thing worth being able to provoke on purpose, and the message names
      // what was wrong with the payload.
      setError(failure instanceof Error ? failure : new Error('The answer could not be marked.'))
      setSubmission(null)
    }
  }

  async function peek() {
    setError(null)
    try {
      setPeekedKey(await getTesterAnswerKeyFor(rehearsal.type, rehearsal.id))
    } catch (failure) {
      setError(failure instanceof Error ? failure : new Error('The answer key could not be read.'))
    }
  }

  /* The key on screen, and whose it is. An answered attempt wins: its pools are
   * ordered around what was actually typed, which is the whole point of sending
   * the submission with the request. */
  const answerKey = verdict?.answer_key ?? peekedKey

  const verdictTone = useMemo(() => {
    if (!verdict) return null
    return verdict.is_correct ? 'correct' : 'wrong'
  }, [verdict])

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <SectionHeading>Simulation</SectionHeading>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => restart()}>
              <RotateCcw size={13} aria-hidden />
              Run again
            </Button>
            {/* A seed, not a shuffle: the new order has to be reproducible, or
                "it comes out wrong sometimes" is not a bug anybody can chase. */}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => restart(`deal-${Date.now().toString(36)}`)}
            >
              <Dices size={13} aria-hidden />
              Deal again
            </Button>
            <Button variant="secondary" size="sm" onClick={peek} disabled={!!answerKey}>
              <Eye size={13} aria-hidden />
              Reveal answer
            </Button>
          </div>
        </div>

        {/* The countdown lives above the board here rather than in a match
            header, because there is no scoreboard to sit beside — but it is the
            same bar, reading the same clock. */}
        <Countdown
          clock={clock}
          label={clock.started ? undefined : taskBeatDone ? 'Reading…' : 'Task…'}
        />

        {/* What a player would be looking at, alone on a black screen, right
            now (`PreQuestionInfo`). Shown for the same beat the server pays
            for, so a question whose instruction is wrong is wrong here at the
            moment it would be wrong in a match. */}
        {!taskBeatDone && (
          <p className="rounded-tile border border-volt/30 bg-volt/8 px-3 py-2.5 text-center font-display text-sm font-bold text-volt motion-safe:animate-pop-in">
            {rehearsal.board.pre_question_info}
          </p>
        )}

        <QuestionBoard
          key={`${rehearsal.id}:${seed}:${runId}`}
          question={rehearsal.board}
          hints={hints}
          submission={submission}
          verdict={verdictTone}
          locked={locked}
          // No clock runs in a rehearsal, so there is no instant to act on:
          // the one board that submits itself at the wire (`NameAsManyBoard`)
          // simply waits for the maintainer to press the button, which is the
          // behaviour a rehearsal wants anyway.
          deadlineAt={null}
          onAnswer={(answer) => void onAnswer(answer)}
          revealOptions={clock.started}
        />

        {clock.expired && !submission && (
          <p className="rounded-tile border border-idle/30 bg-idle/8 px-3 py-2 text-center text-sm text-idle">
            Out of time — which is exactly what a player gets. Run it again to
            answer.
          </p>
        )}

        {error && (
          <p role="alert" className="text-sm text-wrong">
            {error.message}
          </p>
        )}
      </Card>

      {verdict && <RehearsalVerdict verdict={verdict} />}

      {answerKey && (
        <AnswerKeyPanel
          question={rehearsal.board}
          answerKey={answerKey}
          verdict={verdict}
          peeked={!verdict}
        />
      )}
    </div>
  )
}
