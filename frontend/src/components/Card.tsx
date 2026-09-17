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
const EDGE: Record<Edge, string> = {
  court: 'motion-safe:hover:shadow-edge-court',
  volt: 'motion-safe:hover:shadow-edge-volt',
  gold: 'motion-safe:hover:shadow-edge-gold',
  correct: 'motion-safe:hover:shadow-edge-correct',
  wrong: 'motion-safe:hover:shadow-edge-wrong',
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
  border = 'border-chalk/7 border-t-chalk/12',
  bg = 'bg-panel',
  ...rest
}: CardProps<E>) {
  const As = as ?? 'div'
  const interactiveClasses = interactive
    ? `transition-all duration-200 hover:border-chalk/20 hover:bg-raised motion-safe:hover:-translate-y-0.5 ${
        edge ? EDGE[edge] : 'hover:shadow-elevated'
      }`
    : 'shadow-card'
  return (
    <As
      className={`rounded-card border ${border} ${bg} ${interactiveClasses} ${className}`.trim()}
      {...rest}
    >
      {children}
    </As>
  )
}
