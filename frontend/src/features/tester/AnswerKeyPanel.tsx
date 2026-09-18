import { Key } from 'lucide-react'
import { Card } from '../../components/Card'
import { SectionHeading } from '../../components/SectionHeading'
import { describeAnswerKey } from '../matches/answerKey/reveals'
import type {
  AnswerKey,
  PlayQuestion,
  PlayerAnswerRecord,
  TesterVerdict,
} from '../../lib/api/types'

/*
 * What was actually right — the box score's own reveal, opened flat.
 *
 * `describeAnswerKey` is reused rather than re-written, and that reuse is the
 * point: it is the client's end of `apps.questions.api.reveal`, it knows how
 * each of the eight shapes reads back (ids into option text, a grid into its
 * headings, a pool with the tail counted), and a second implementation over
 * here would be a second thing to keep in step with the backend — and the one
 * that gets it wrong would be the one nobody notices, since only maintainers
 * ever see this page.
 *
 * ## The one thing this does differently, and why
 *
 * That helper answers with either an `inline` reveal or a `modal` one, and the
 * rule behind the split is about a *table row*: a box score reveals an answer
 * in a cell beside the two players, so anything bigger than a short string has
 * to go behind a button or it costs the row its shape.
 *
 * There is no table here and no row to protect. This is a page about one
 * question, and the answer is what it is for — so a `modal` reveal is rendered
 * **in place**, with its title above it. Keeping the button would be asking a
 * maintainer to click through to the thing they navigated here to see.
 *
 * ## `mine`, and why a peek is not an empty answer
 *
 * The reveal marks the first entry of a pool as "your answer" only when the
 * reader actually got it right — the server floats a correct spelling to the
 * front, and decorating it otherwise would credit a wrong answer with a green
 * tick. So an answered attempt passes a record built from its own verdict, and
 * a peek (`Reveal answer` with nothing submitted) passes `null`: nobody
 * answered, so there is nothing of anybody's to mark.
 */
export function AnswerKeyPanel({
  question,
  answerKey,
  verdict,
  peeked,
}: {
  question: PlayQuestion
  answerKey: AnswerKey
  /** The attempt this key came back with, or null when it was simply asked
   *  for. Used only to order and mark a pool — never to decide what is shown. */
  verdict: TesterVerdict | null
  /** True when the key was revealed without an answer, which is worth saying
   *  out loud: an empty-looking reveal beside a board nobody played is
   *  otherwise indistinguishable from a bug. */
  peeked: boolean
}) {
  // `describeAnswerKey` takes a box score's `PlayerAnswerRecord`. A rehearsal
  // has no such row and never will — nothing is written — so one is built from
  // the verdict for the two fields the reveal actually reads (`is_correct`,
  // and `submitted` for the pool ordering the server already applied). The
  // match-only figures are filled with what they honestly are here: this
  // attempt's own numbers, and a timestamp of now.
  const mine: PlayerAnswerRecord | null = verdict
    ? {
        submitted: verdict.submitted,
        is_correct: verdict.is_correct,
        score: verdict.score,
        points: verdict.points,
        response_time_ms: verdict.elapsed_ms,
        answered_at: new Date().toISOString(),
      }
    : null

  const reveal = describeAnswerKey({ question, answerKey, mine })

  return (
    <Card border="border-gold/30" className="flex flex-col gap-3 p-4 sm:p-5">
      <SectionHeading className="!text-gold">
        <span className="flex items-center gap-1.5">
          <Key size={13} aria-hidden />
          {reveal.kind === 'modal' ? reveal.title : 'The answer'}
        </span>
      </SectionHeading>

      {reveal.kind === 'inline' ? (
        <p className="font-display text-xl font-bold text-gold">{reveal.content}</p>
      ) : (
        <>
          {reveal.description && <p className="text-sm text-ash">{reveal.description}</p>}
          {reveal.body}
        </>
      )}

      {peeked && (
        <p className="text-xs text-ash">
          Revealed without answering — nothing on the board above was submitted.
        </p>
      )}
    </Card>
  )
}
