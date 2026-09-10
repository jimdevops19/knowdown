import type { ImageAnswerQuestion } from '../../../lib/api/types'
import { OPTION_LETTERS, type BoardProps } from './types'

/*
 * Pick one of four pictures — "which of these is Kobe?".
 *
 * Its own board rather than a variant of the single-answer one, for the reason
 * the backend keeps them as separate types even though their submission bodies
 * are identical: the *option* is a different kind of thing. A text option is a
 * line to read; an image option is a thing to recognise, and recognition is
 * faster than reading. So the grid is two columns even on a phone — four
 * pictures at once beats one picture and three off-screen when the whole game
 * is how fast you know it.
 *
 * `label` is the backend's alt text, and it is *safe*: it names which option
 * this is ("Kobe Bryant" beside a photo of Kobe Bryant), never whether it is
 * the right one. It is not shown, because showing it would turn a picture
 * question into a text question — but it must be on the `alt`, or the question
 * is unanswerable with a screen reader.
 */
export function ImageAnswerBoard({
  question,
  submission,
  verdict,
  locked,
  onAnswer,
}: BoardProps<ImageAnswerQuestion>) {
  const pickedId =
    submission?.type === 'image-answer' || submission?.type === 'single-answer'
      ? submission.option_id
      : null

  return (
    <div className="grid grid-cols-2 gap-2.5 sm:gap-3">
      {question.options.map((option, index) => {
        const picked = option.id === pickedId
        const ring = picked
          ? verdict === 'correct'
            ? 'border-correct shadow-glow-correct motion-safe:animate-verdict-correct'
            : verdict === 'wrong'
              ? 'border-wrong shadow-glow-wrong motion-safe:animate-verdict-wrong'
              : 'border-court shadow-glow-violet'
          : locked
            ? 'border-white/8 opacity-50'
            : 'border-white/10 hover:border-court/60 active:scale-[0.985]'

        return (
          <button
            key={option.id}
            type="button"
            disabled={locked}
            aria-pressed={picked}
            onClick={() => onAnswer({ type: 'image-answer', option_id: option.id })}
            className={`relative overflow-hidden rounded-tile border-2 bg-panel transition-all duration-150 disabled:pointer-events-none ${ring}`}
          >
            <img
              src={option.image}
              alt={option.label}
              // A fixed aspect ratio so the grid is laid out before a single
              // image has loaded: options popping into a taller row mid-clock
              // would move the tile out from under a thumb already moving.
              className="aspect-square w-full object-cover"
              loading="eager"
            />
            <span className="absolute left-2 top-2 flex h-6 w-6 items-center justify-center rounded-lg bg-void/70 font-display text-xs font-bold text-chalk backdrop-blur-sm">
              {OPTION_LETTERS[index] ?? index + 1}
            </span>
          </button>
        )
      })}
    </div>
  )
}
