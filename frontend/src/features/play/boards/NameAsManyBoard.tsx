import { useEffect, useRef, useState } from 'react'
import { Plus, X } from 'lucide-react'
import type { NameAsManyQuestion } from '../../../lib/api/types'
import { Input } from '../../../components/Input'
import { Button } from '../../../components/Button'
import { type BoardProps } from './types'

/*
 * "Name as many players as you can with 1,000+ career three-pointers."
 *
 * The board where the player writes a *list*, and the only one where the clock
 * is a budget to spend rather than a deadline to beat — the server scores this
 * type without a speed multiplier (`apps.matches.constants.SPEED_SCORED_TYPES`)
 * precisely so that typing one name and hitting send is never the winning play.
 *
 * Four decisions, and each of them is about the same thing: giving the player
 * every second for thinking and none for fighting the UI.
 *
 *  - **Enter adds a name; it does not submit.** The field is the fast path and
 *    it is used a dozen times a question, so the key under the thumb has to be
 *    the one used a dozen times. Submitting is a separate, deliberate button.
 *  - **Nothing is graded as it is typed.** A name lands as a plain chip, not a
 *    green or red one. The server never tells this board whether a name counts
 *    — see `NameAsManyQuestion` — because a per-name verdict would let anybody
 *    use the server as a lookup and have the question answer itself.
 *  - **Duplicates are absorbed, not rejected.** Typing a name already in the
 *    list clears the field and moves on: the payload may not repeat a name (the
 *    backend refuses one that does), and a player racing a clock should meet
 *    that rule as "already got it", not as an error message.
 *  - **The list submits itself at the wire.** A player typing when the clock
 *    runs out would otherwise score nothing at all — the one failure this mode
 *    can produce that has nothing to do with knowing basketball. See
 *    `AUTO_SUBMIT_LEAD_MS`.
 *
 * Autocomplete, autocorrect and spellcheck are off for the reason
 * `FreeTextBoard` turns them off: a phone helpfully correcting a surname would
 * cost somebody the question, and a browser offering their earlier answers
 * would be a cheat sheet built from their own history.
 */

/**
 * How long before the server closes the question this board sends what it has.
 *
 * Far enough back that the frame still lands inside the clock the *server* is
 * keeping (`submit_answer` refuses one that arrives late), close enough that it
 * costs a player nothing — this type is not scored on speed, so a submission at
 * 29.2s is worth exactly what the same submission at 2s is worth. A second is
 * the round trip plus the margin for a phone on a slow network.
 */
const AUTO_SUBMIT_LEAD_MS = 1_000

export function NameAsManyBoard({
  question,
  submission,
  deadlineAt,
  locked,
  onAnswer,
}: BoardProps<NameAsManyQuestion>) {
  const [names, setNames] = useState<string[]>([])
  const [draft, setDraft] = useState('')

  const committed = submission?.type === 'name-as-many' ? submission.names : null
  const shown = committed ?? names
  const full = shown.length >= question.max_names

  // Read through a ref by the timer below, so arming it does not depend on the
  // list — a timer re-armed on every keystroke is a timer that fires late on
  // the one question where somebody is typing right up to the whistle. Written
  // in an effect rather than during render: a ref is not rendering state, and
  // the timer that reads it only ever fires after one has committed.
  const latest = useRef(shown)
  useEffect(() => {
    latest.current = shown
  })

  const submit = (list: string[]) => {
    if (list.length === 0) return
    onAnswer({ type: 'name-as-many', names: list })
  }

  const add = () => {
    const name = draft.trim()
    if (!name || locked || full) return
    setDraft('')
    // Folded the way the server folds it, so "already got it" here and
    // "malformed" there can never disagree about what a repeat is.
    if (shown.some((existing) => fold(existing) === fold(name))) return
    setNames([...shown, name])
  }

  const remove = (name: string) => {
    if (locked || committed) return
    setNames(shown.filter((existing) => existing !== name))
  }

  useEffect(() => {
    if (deadlineAt === null || committed !== null || locked) return
    const delay = deadlineAt - AUTO_SUBMIT_LEAD_MS - Date.now()
    // Already past the lead: send immediately rather than never. A board
    // mounted this late has nothing to lose by trying — the server refuses a
    // late frame, which costs the player exactly what silence would have.
    const timer = window.setTimeout(() => submit(latest.current), Math.max(0, delay))
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deadlineAt, committed, locked])

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault()
        add()
      }}
    >
      <div className="flex gap-2">
        <Input
          // Safe as a mount-time prop because the board is remounted per
          // question (see QuestionBoard's `key`): it focuses once, when the
          // question opens, and never steals the caret mid-typing.
          autoFocus
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          disabled={locked || full || committed !== null}
          maxLength={255}
          placeholder={full ? 'That is plenty' : 'Type a name, press enter…'}
          aria-label="Add a name"
          enterKeyHint="enter"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="words"
          spellCheck={false}
          className="h-12 flex-1"
        />
        <Button
          type="submit"
          variant="secondary"
          disabled={locked || full || committed !== null || draft.trim().length === 0}
          aria-label="Add this name"
        >
          <Plus size={18} aria-hidden />
        </Button>
      </div>

      {/* The list reads newest-first: the name just added is the one the player
          looks at to check it landed, and on a phone the bottom of a long list
          is behind the keyboard. */}
      <ul className="flex flex-wrap gap-1.5" aria-label="Names you have given">
        {[...shown].reverse().map((name) => (
          <li key={name}>
            <span className="inline-flex items-center gap-1 rounded-btn border border-chalk/10 bg-panel/60 px-2.5 py-1 text-sm text-chalk">
              {name}
              {!committed && !locked && (
                <button
                  type="button"
                  onClick={() => remove(name)}
                  aria-label={`Remove ${name}`}
                  className="text-ash transition-colors hover:text-wrong"
                >
                  <X size={14} aria-hidden />
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>

      <p className="text-center text-xs text-ash">
        {shown.length === 0 ? 'No names yet' : `${shown.length} name${shown.length === 1 ? '' : 's'}`}
        {' · '}
        {/* The scoring rule, stated plainly. It is not a clue — it says what a
            name is *worth*, never which names are right — and without it the
            mode looks like "type five names and stop", which is the one
            strategy it is built to beat. */}
        the deeper the cut, the more it pays ({question.target_score} pts for full credit)
      </p>

      {!committed && (
        <Button
          size="full"
          variant="accent"
          type="button"
          disabled={locked || shown.length === 0}
          onClick={() => submit(shown)}
        >
          {shown.length === 0 ? 'Start naming' : `Lock in ${shown.length}`}
        </Button>
      )}
    </form>
  )
}

/** The comparison form of a name — the client's copy of the backend's
 *  `apps.questions.matching.normalise_answer`, and it has to stay one: this is
 *  what decides a repeat is already in the list, and the server decides the
 *  same thing the same way before calling one malformed. */
function fold(name: string): string {
  return name.trim().split(/\s+/).join(' ').toLowerCase()
}
