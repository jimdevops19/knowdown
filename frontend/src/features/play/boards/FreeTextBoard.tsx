import { useState } from 'react'
import { CornerDownLeft } from 'lucide-react'
import type { FreeTextQuestion } from '../../../lib/api/types'
import { Input } from '../../../components/Input'
import { Button } from '../../../components/Button'
import { type BoardProps } from './types'

/*
 * Type the answer. The hardest question type to answer under a clock, and the
 * one where the board can do the most to help.
 *
 * Three decisions worth stating:
 *
 *  - **Autofocus, and a keyboard that submits.** Ten seconds is not enough to
 *    find a field, and Enter is the only sane commit on a phone keyboard —
 *    which is why `enterKeyHint="send"` labels that key "Send" rather than
 *    leaving it as a newline nobody wants.
 *  - **Nothing is corrected on the way out.** The text goes verbatim. Trimming
 *    and casefolding are the evaluator's business, and what gets recorded
 *    should be the thing the player can be shown afterwards — not a normalized
 *    key they never wrote.
 *  - **`maxLength` matches the server's cap** (255), so the obvious mistake is
 *    stopped in the field rather than refused a round trip later, with a clock
 *    running the whole time.
 *
 * Autocomplete, autocorrect and spellcheck are all off. This is a *quiz*: a
 * phone keyboard helpfully correcting "Wilt" to "Will" would cost somebody the
 * question, and a browser offering their previous answers would be a cheat
 * sheet built out of their own history.
 */
export function FreeTextBoard({
  submission,
  verdict,
  locked,
  onAnswer,
}: BoardProps<FreeTextQuestion>) {
  const [text, setText] = useState('')

  const committed = submission?.type === 'free-text' ? submission.text : null
  const value = committed ?? text
  const canSubmit = !locked && text.trim().length > 0

  const submit = () => {
    if (!canSubmit) return
    onAnswer({ type: 'free-text', text })
  }

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <Input
        // Safe as a mount-time prop rather than an effect because the board is
        // remounted per question (see QuestionBoard's `key`): it focuses once,
        // when a question opens, and never steals the caret mid-typing.
        autoFocus
        value={value}
        onChange={(event) => setText(event.target.value)}
        disabled={locked}
        maxLength={255}
        placeholder="Type your answer…"
        aria-label="Your answer"
        enterKeyHint="send"
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        spellCheck={false}
        className={`h-14 text-center font-display text-lg ${
          verdict === 'correct'
            ? 'border-correct focus:border-correct focus:ring-correct/25'
            : verdict === 'wrong'
              ? 'border-wrong focus:border-wrong focus:ring-wrong/25'
              : ''
        }`}
      />
      {!committed && (
        <Button size="full" variant="accent" type="submit" disabled={!canSubmit}>
          Lock it in
          <CornerDownLeft size={18} aria-hidden />
        </Button>
      )}
    </form>
  )
}
