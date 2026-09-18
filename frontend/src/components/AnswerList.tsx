/*
 * A stack of answers, one per row.
 *
 * The plainest thing in this family and the one the others are built out of:
 * `AnswerPoolList` is this plus a line about the answers that were not sent,
 * and a box score's "what they filled in" is this on its own. Extracted so the
 * key and the guess beside it are laid out by one rule — a set of six is six
 * rows whether it was right or wrong, and the only thing that should differ
 * between those two readings is the colour.
 *
 * `leading` marks the first row as the reader's own answer. It is a prop rather
 * than something inferred here because only the caller knows whether the
 * player was actually right, and a list that decorated its first row on its own
 * would sooner or later put a tick beside a wrong answer.
 */
export function AnswerList({
  items,
  leading,
  leadingNote = 'your answer',
}: {
  items: string[]
  leading?: boolean
  leadingNote?: string
}) {
  return (
    <ul className="flex flex-col gap-1.5">
      {items.map((item, index) => (
        <li
          key={item}
          className={`rounded-tile border px-3 py-2 text-sm ${
            leading && index === 0
              ? 'border-correct/40 bg-correct/8 text-correct'
              : 'border-chalk/8 bg-panel/60 text-chalk'
          }`}
        >
          {item}
          {leading && index === 0 && (
            <span className="ml-2 text-xs text-ash">{leadingNote}</span>
          )}
        </li>
      ))}
    </ul>
  )
}
