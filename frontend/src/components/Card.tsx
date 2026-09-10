import type { ComponentPropsWithoutRef, ElementType, ReactNode } from 'react'

/*
 * The base surface every panel, card and list row sits on — a glass panel with
 * a hairline border and soft depth. `interactive` makes the whole card a hover
 * target: it lifts, brightens its border and optionally takes a coloured glow,
 * used when the card is itself a link.
 *
 * Padding and layout stay the caller's job via `className`, since they vary per
 * use. Polymorphic via `as` (e.g. `as={Link} to="…"`) so a card can *be* the
 * clickable element rather than wrapping one — which matters for the tap target
 * on a phone, where a link inside a card leaves most of the card dead.
 */
type Glow = 'violet' | 'cyan' | 'gold' | 'correct' | 'wrong'
const GLOW: Record<Glow, string> = {
  violet: 'motion-safe:hover:shadow-glow-violet',
  cyan: 'motion-safe:hover:shadow-glow-cyan',
  gold: 'motion-safe:hover:shadow-glow-gold',
  correct: 'motion-safe:hover:shadow-glow-correct',
  wrong: 'motion-safe:hover:shadow-glow-wrong',
}

type CardOwnProps<E extends ElementType> = {
  children: ReactNode
  interactive?: boolean
  /** Coloured glow on hover (only meaningful with `interactive`). */
  glow?: Glow
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
  glow,
  as,
  className = '',
  border = 'border-white/6',
  bg = 'bg-panel/80',
  ...rest
}: CardProps<E>) {
  const As = as ?? 'div'
  const interactiveClasses = interactive
    ? `transition-all duration-200 hover:border-white/15 motion-safe:hover:-translate-y-0.5 ${
        glow ? GLOW[glow] : 'hover:shadow-elevated'
      }`
    : 'shadow-card'
  return (
    <As
      className={`rounded-card border ${border} ${bg} backdrop-blur-md ${interactiveClasses} ${className}`.trim()}
      {...rest}
    >
      {children}
    </As>
  )
}
