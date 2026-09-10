import type { AnswerSubmission, PlayQuestion } from '../../../lib/api/types'

/*
 * The contract every board implements.
 *
 * One board per question type, the same way the backend has one model, one
 * schema, one serializer and one evaluator per type — five sibling registries
 * that have to agree, and a test on each side that walks them so none of the
 * five can be the one that was forgotten (see `QUESTION_BOARDS` in
 * `../QuestionBoard.tsx` for this side's).
 *
 * The props are deliberately narrow. A board renders a question and reports an
 * answer; it does not know about the socket, the clock, the opponent or the
 * score. Everything it needs to decide what to paint is here:
 */
export interface BoardProps<Q extends PlayQuestion = PlayQuestion> {
  question: Q
  /**
   * What this player has already submitted for this question, if anything.
   * Set the moment the answer goes out — before the server rules on it — so a
   * tapped tile can show as taken rather than sitting inert through a round
   * trip and inviting a second tap.
   */
  submission: AnswerSubmission | null
  /**
   * The server's verdict for *this* player, once the question closed. Null
   * while the clock is running.
   *
   * There is no "and here is the right answer" prop, because there is no such
   * message: `question.result` says whether you were right and does not publish
   * the key. A question can come up again in a later match, and a client that
   * had been handed every answer it ever saw would be a client worth scraping.
   */
  verdict: 'correct' | 'wrong' | null
  /** The board no longer takes input — answered, closed, or the clock is out. */
  locked: boolean
  /** Submit. The caller decides whether it goes anywhere. */
  onAnswer: (submission: AnswerSubmission) => void
}

/** Grid classes shared by the option-list boards, so a two-option question and
 *  a four-option one are laid out by the same rule: one column on a phone
 *  (thumb-width tiles, no horizontal eye movement under the clock), two from
 *  `sm` up where the row is wide enough for a pair to be read at once. */
export const OPTION_GRID = 'grid gap-2.5 sm:grid-cols-2'

/** Option letters, so every board labels its tiles A/B/C/D the same way. Here
 *  rather than beside <AnswerTile> so that file exports only components, which
 *  is what keeps React Fast Refresh working on it. */
export const OPTION_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'] as const
