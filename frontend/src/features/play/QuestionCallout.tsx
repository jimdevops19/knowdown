import { ListOrdered } from 'lucide-react'
import type { PlayQuestion } from '../../lib/api/types'

/*
 * "This one is not a normal question."
 *
 * Most types on this board are answered the way the board looks: tiles are
 * tapped, boxes are typed into. Ordering is the type where the control looks
 * like every other one and means something different — the tiles are not
 * options to choose between, they are positions to assign, and a player who
 * reads it as "pick the right one" has already lost the question before the
 * clock starts.
 *
 * So the instruction is not left to the board. It is hoisted up here, *above*
 * the question and outside the options reveal, which means it lands with the
 * question text and stands alone for the whole read delay — the beat the match
 * screen deliberately holds before the tiles appear. By the time there is
 * anything to tap, "tap them in order" has already been on screen for a second
 * with nothing competing for the glance.
 *
 * It stays up while the board is played rather than fading, because the rule
 * ("earliest first") is needed at the moment of the *last* tap as much as the
 * first, and a rule that has to be remembered is a rule half the players will
 * get backwards.
 *
 * Only the types whose interaction is genuinely unlike the rest belong here.
 * A callout on every question is a callout on none of them — the eye stops
 * reading a strip that is always there and always says something obvious, and
 * the one time it matters it will be skipped with the others.
 */
export function QuestionCallout({ question }: { question: PlayQuestion }) {
  if (question.type !== 'ordering') return null

  return (
    <div className="flex items-start gap-2.5 rounded-tile border border-volt/30 bg-volt/8 px-3 py-2.5 motion-safe:animate-pop-in">
      <ListOrdered size={18} className="mt-0.5 shrink-0 text-volt" aria-hidden />
      <div className="min-w-0">
        <p className="font-display text-[11px] font-bold uppercase tracking-[0.12em] text-volt">
          Ordering question — tap the options in order
        </p>
        {/* The question's own rule, and the loud half: "tap them in order" is
            the interaction, this is the sequence being asked for. */}
        <p className="text-sm font-semibold text-chalk">{question.instruction}</p>
      </div>
    </div>
  )
}
