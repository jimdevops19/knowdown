import { Check, X } from 'lucide-react'
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
/** The same lane colours <AnswerTile> gives its keys, so A is the orange one
 *  whether the options are sentences or photographs. */
const LANE_FILLS = ['bg-court', 'bg-room-a', 'bg-room-b', 'bg-rival'] as const

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
        /*
         * The one board whose state cannot be the surface: the surface is the
         * photograph, and it is the thing being asked about. So a picture tile
         * keeps the ring — but it takes the lip and the press travel every other
         * control now has, so it is still an object rather than a framed image,
         * and the verdict gets a solid chip in the corner so the answer is not
         * carried by a 2px outline alone.
         */
        const ring = picked
          ? verdict === 'correct'
            ? 'border-correct shadow-lip-correct motion-safe:animate-verdict-correct'
            : verdict === 'wrong'
              ? 'border-wrong shadow-lip-wrong motion-safe:animate-verdict-wrong'
              : 'border-court shadow-lip-court'
          : locked
            ? 'border-chalk/8 opacity-50'
            : 'pressable border-chalk/16 shadow-lip-plate hover:border-court'

        return (
          <button
            key={option.id}
            type="button"
            disabled={locked}
            aria-pressed={picked}
            onClick={() => onAnswer({ type: 'image-answer', option_id: option.id })}
            className={`relative overflow-hidden rounded-tile border-2 bg-panel disabled:pointer-events-none ${ring}`}
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
            {/* The lane key, in the same four colours the text boards use — a
                solid chip rather than a smoked-glass one, because on top of a
                photograph a translucent badge is legible against exactly the
                images that happen to be dark. */}
            <span
              className={`absolute left-2 top-2 flex h-6 w-6 items-center justify-center rounded-[9px] font-display text-xs font-bold text-void ${
                LANE_FILLS[index % LANE_FILLS.length]
              }`}
            >
              {OPTION_LETTERS[index] ?? index + 1}
            </span>
            {picked && verdict && (
              <span
                aria-hidden
                className={`absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-[9px] text-void ${
                  verdict === 'correct' ? 'bg-correct' : 'bg-wrong'
                }`}
              >
                {verdict === 'correct' ? (
                  <Check size={18} strokeWidth={3} />
                ) : (
                  <X size={18} strokeWidth={3} />
                )}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
