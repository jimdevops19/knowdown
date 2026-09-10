import { useMemo, useState } from 'react'
import type { MatrixCellSubmission, MatrixQuestion } from '../../../lib/api/types'
import { Input } from '../../../components/Input'
import { Button } from '../../../components/Button'
import { type BoardProps } from './types'

/*
 * A grid to fill in — "which team did each of these players win a title with,
 * in each of these years".
 *
 * Two things make this board unlike the rest.
 *
 * **The grid is sparse.** The cells a question actually asks for are a subset
 * of rows × columns, which is why the payload lists them explicitly; drawing an
 * input in every square would have players spending the clock on squares nobody
 * scores. So the empty intersections are rendered as visibly *not* fields —
 * struck through, not merely disabled — and only the listed cells take input.
 *
 * **A partial answer is a real answer.** This is the one type the server scores
 * per cell, so credit is a fraction rather than a boolean: three of five cells
 * right is worth three-fifths, not nothing. That changes what the submit button
 * is for — filling in what you know and sending it is the correct play, so the
 * button is enabled from the first filled cell rather than waiting for a
 * complete grid the way the ordering board does.
 *
 * On a phone the grid scrolls sideways inside its own container. The page it
 * sits on must not scroll (an answer tile below the fold is an answer the clock
 * runs out on), so the overflow is deliberately local: `overflow-x-auto` here,
 * never on the board's parent.
 */
export function MatrixBoard({
  question,
  submission,
  verdict,
  locked,
  onAnswer,
}: BoardProps<MatrixQuestion>) {
  const [values, setValues] = useState<Record<string, string>>({})

  // The sparse set, as a lookup — a cell is askable only if it is in this.
  const askable = useMemo(
    () => new Set(question.cells.map((cell) => cellKey(cell.row_id, cell.column_id))),
    [question.cells],
  )

  const committed =
    submission?.type === 'matrix'
      ? Object.fromEntries(
          submission.cells.map((cell) => [cellKey(cell.row_id, cell.column_id), cell.answer]),
        )
      : null
  const shown = committed ?? values

  const filled = Object.entries(shown).filter(([, answer]) => answer.trim().length > 0)

  const submit = () => {
    const cells: MatrixCellSubmission[] = filled.map(([key, answer]) => {
      const [rowId, columnId] = key.split(':').map(Number)
      return { row_id: rowId, column_id: columnId, answer }
    })
    if (cells.length === 0) return
    onAnswer({ type: 'matrix', cells })
  }

  const tone =
    verdict === 'correct'
      ? 'border-correct/60'
      : verdict === 'wrong'
        ? 'border-wrong/60'
        : 'border-white/8'

  return (
    <div className="flex flex-col gap-3">
      <div className={`overflow-x-auto rounded-tile border ${tone} bg-panel/60`}>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              {/* The corner: empty, and sticky so the row headings stay
                  readable once the grid is scrolled sideways. */}
              <th className="sticky left-0 z-10 bg-raised px-3 py-2" />
              {question.columns.map((column) => (
                <th
                  key={column.id}
                  scope="col"
                  className="whitespace-nowrap bg-raised px-3 py-2 text-left font-display text-xs font-semibold uppercase tracking-wide text-ash"
                >
                  {column.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {question.rows.map((row) => (
              <tr key={row.id} className="border-t border-white/6">
                <th
                  scope="row"
                  className="sticky left-0 z-10 whitespace-nowrap bg-raised px-3 py-2 text-left font-medium text-chalk"
                >
                  {row.title}
                </th>
                {question.columns.map((column) => {
                  const key = cellKey(row.id, column.id)
                  if (!askable.has(key)) {
                    return (
                      <td key={column.id} className="px-3 py-2">
                        <span
                          aria-hidden
                          className="block h-px w-full bg-white/10"
                          title="Not asked"
                        />
                      </td>
                    )
                  }
                  return (
                    <td key={column.id} className="px-2 py-1.5">
                      <Input
                        size="sm"
                        value={shown[key] ?? ''}
                        disabled={locked}
                        maxLength={255}
                        autoComplete="off"
                        autoCorrect="off"
                        spellCheck={false}
                        aria-label={`${row.title}, ${column.title}`}
                        onChange={(event) =>
                          setValues((current) => ({ ...current, [key]: event.target.value }))
                        }
                        className="min-w-28"
                      />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!committed && (
        <Button
          size="full"
          variant="accent"
          disabled={locked || filled.length === 0}
          onClick={submit}
        >
          {filled.length === 0
            ? 'Fill in what you know'
            : `Lock in ${filled.length} of ${question.cells.length}`}
        </Button>
      )}
    </div>
  )
}

/** One intersection's key. Row and column are named **by id**, never by title:
 *  the client was sent ids, and matching titles back would make a player's
 *  answer depend on the exact spelling of a heading. */
function cellKey(rowId: number, columnId: number): string {
  return `${rowId}:${columnId}`
}
