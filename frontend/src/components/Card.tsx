import type { ComponentPropsWithoutRef, ElementType, ReactNode } from 'react'

/*
 * The base surface every panel, card and list row sits on — an opaque plate
 * with a hairline edge and shadow depth. `interactive` makes the whole card a
 * hover target: it lifts, brightens its edge, and optionally takes a coloured
 * keyline, used when the card is itself a link.
 *
 * Opaque, and no `backdrop-blur`. The frosted-glass version this replaces left
 * every panel a slightly different colour depending on what had scrolled behind
 * it, and paid for a backdrop composite per surface on phones — with a dozen
 * cards on a ladder screen, that is the difference between a list that flicks
 * and one that drags.
 *
 * Two pixels of border and a hard 3px shelf under it, where this was a hairline
 * and a 24px blur. A card is not pressable, so it doesn't get a button's full
 * lip — but it gets the same idea at lower amplitude, which is what makes a list
 * of them read as tiles laid on a table rather than as rows in a document. A
 * blurred shadow does the opposite: it says "floating panel", which is a
 * dashboard's vocabulary, and against a dark ground it mostly just reads as
 * smudge.
 *
 * Padding and layout stay the caller's job via `className`, since they vary per
 * use. Polymorphic via `as` (e.g. `as={Link} to="…"`) so a card can *be* the
 * clickable element rather than wrapping one — which matters for the tap target
 * on a phone, where a link inside a card leaves most of the card dead.
 */

/*
 * The hover keyline, named by *role* rather than by hue.
 *
 * The old spelling of this type was `'violet' | 'cyan' | …` — literal colours,
 * which is how a palette gets welded to the components using it: renaming the
 * brand colour then means touching every call site, or leaving a keyline still
 * asking for violet on an orange card forever. These names survive the next
 * repaint, and they also state the rule the palette runs on — a card's keyline
 * says what the card *is* (yours, live, ranked, right, wrong), and anything
 * that is none of those gets no colour at all.
 */
type Edge = 'court' | 'volt' | 'gold' | 'correct' | 'wrong'
/*
 * Not gated behind `motion-safe:` any more: these are keylines, not motion —
 * the only thing that ever moved was the lift that has now gone. A coloured
 * edge on hover is a colour change, and nobody asked for fewer of those.
 */
const EDGE: Record<Edge, string> = {
  court: 'hover:shadow-edge-court',
  volt: 'hover:shadow-edge-volt',
  gold: 'hover:shadow-edge-gold',
  correct: 'hover:shadow-edge-correct',
  wrong: 'hover:shadow-edge-wrong',
}

type CardOwnProps<E extends ElementType> = {
  children: ReactNode
  interactive?: boolean
  /** Coloured keyline on hover (only meaningful with `interactive`). */
  edge?: Edge
  as?: E
  className?: string
  border?: string
  bg?: string
}

type CardProps<E extends ElementType> = CardOwnProps<E> &
  Omit<ComponentPropsWithoutRef<E>, keyof CardOwnProps<E>>

export function Card<E extends ElementType = 'div'>({
  children,
  interactive = false,
  edge,
  as,
  className = '',
  // The edge catches the light at the top and falls away below, so a card
  // reads as a plate lying under the floodlight rather than as a rectangle
  // outlined on all four sides.
  border = 'border-chalk/14 border-t-chalk/20',
  bg = 'bg-panel',
  ...rest
}: CardProps<E>) {
  const As = as ?? 'div'
  /*
   * An interactive card keeps the shelf and presses into it, rather than lifting
   * away from the pointer. The lift was a hover trick — invisible on the phone
   * this app is built for — while a card that sinks under a thumb is the same
   * grammar every button here now uses, and a tappable card is a big button.
   */
  const interactiveClasses = interactive
    ? `pressable shadow-card hover:border-chalk/28 hover:bg-raised ${edge ? EDGE[edge] : ''}`
    : 'shadow-card'
  return (
    <As
      className={`rounded-card border-2 ${border} ${bg} ${interactiveClasses} ${className}`.trim()}
      {...rest}
    >
      {children}
    </As>
  )
}
