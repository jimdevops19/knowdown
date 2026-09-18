import { Key } from 'lucide-react'
import { TableCell, TableRow } from '../../../components/Table'
import type { AnswerKey, PlayQuestion, PlayerAnswerRecord } from '../../../lib/api/types'
import { RevealCell } from './RevealCell'
import { describeAnswerKey } from './reveals'

/*
 * The third row of a question's table: what was actually right.
 *
 * It sits under the two players rather than above them because a box score is
 * read as a result first and a post-mortem second — you look at who took the
 * question, then at what the answer was. Toned gold, which is neither the
 * correct green nor the wrong red: the key is nobody's answer, it belongs to
 * the question.
 *
 * Whether it lands in the cell or behind a button is `describeAnswerKey`'s
 * decision, made per question — see the rule at the top of `reveals.tsx`.
 *
 * The time and points columns are em dashes on purpose: in a numeric column a
 * dash reads as "not applicable" where a blank reads as "missing", and the
 * answer key took no time and scored nothing.
 */
export function AnswerKeyRow({
  question,
  answerKey,
  mine,
}: {
  question: PlayQuestion
  answerKey: AnswerKey
  /** The reader's own record, used only to mark their answer inside a pool. */
  mine: PlayerAnswerRecord | null
}) {
  return (
    <TableRow>
      <TableCell className="text-ash">Answer</TableCell>
      <TableCell>
        <RevealCell
          reveal={describeAnswerKey({ question, answerKey, mine })}
          tone="text-gold"
          icon={<Key size={14} className="shrink-0" aria-hidden />}
        />
      </TableCell>
      <TableCell align="right" className="text-ash">
        —
      </TableCell>
      <TableCell align="right" className="text-ash">
        —
      </TableCell>
    </TableRow>
  )
}
