import { AnswerList } from './AnswerList'
import type { AnswerPool } from '../lib/api/types'

/*
 * A pool of accepted answers, and an honest line about the ones that are not
 * here.
 *
 * "Name a player who turned out for both these franchises" has as many right
 * answers as the two rosters shared, which runs to hundreds. Listing them is
 * not a reveal, it is a phone book — and the server would not send them anyway:
 * `apps.questions.api.reveal` cuts the pool before it serializes, so
 * `accepted` is everything the client has and `total` is the only evidence the
 * rest existed.
 *
 * That is worth stating plainly in the UI, which is what the tail line does.
 * "… and 17 more" is a *count*, not a teaser for something the page is
 * withholding — there is nothing in the payload to withhold. A player who reads
 * it as "17 answers this screen is hiding from me" has the wrong idea about the
 * screen, but the right idea about the question, which is the part that
 * matters: their answer was one of many, and getting it was not luck.
 *
 * `leading` is the first entry when the player got it right — the server floats
 * their own spelling to the front, so this component gets the ordering for free
 * and only has to mark it.
 */
export function AnswerPoolList({
  pool,
  leading,
  empty = 'No answer recorded.',
}: {
  pool: AnswerPool
  /** Highlight the first entry as *this player's* answer. Off unless the caller
   *  knows they were right — marking it otherwise would credit a wrong answer
   *  with a green tick, which is the one thing a post-mortem must not do. */
  leading?: boolean
  empty?: string
}) {
  const hidden = pool.total - pool.accepted.length

  if (pool.accepted.length === 0) {
    return <p className="text-sm text-ash">{empty}</p>
  }

  return (
    <div className="flex flex-col gap-1.5">
      <AnswerList items={pool.accepted} leading={leading} />
      {hidden > 0 && (
        <p className="nums px-1 text-xs text-ash">
          … and {hidden} more accepted {hidden === 1 ? 'answer' : 'answers'}
        </p>
      )}
    </div>
  )
}
