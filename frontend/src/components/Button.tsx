import type { ComponentPropsWithoutRef, ElementType, ReactNode } from 'react'

/*
 * The app's action button. Violet primary by default, with game-feel motion: a
 * lift and a coloured glow on hover, a press-down on click. Motion is gated
 * behind `motion-safe:` so reduced-motion users get a plain colour change.
 * Polymorphic via `as`, so a submit button and a nav link share one look.
 *
 * `full` is not just a width — it is the phone size. A primary action on a
 * phone is a 48px bar across the thumb's reach, and every screen's main verb
 * ("Find a match", "Sign in") uses it below `sm`.
 */
type ButtonSize = 'sm' | 'md' | 'lg' | 'full'
type ButtonVariant = 'primary' | 'accent' | 'secondary' | 'ghost' | 'danger'

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-4',
  lg: 'h-12 px-6 text-base',
  full: 'h-12 w-full text-base',
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'bg-court text-chalk hover:bg-deep-court motion-safe:hover:shadow-glow-violet',
  // Cyan on near-black. The dark foreground is not a style choice: cyan this
  // bright fails contrast against white text and passes comfortably against the
  // background colour.
  accent: 'bg-volt text-void hover:bg-deep-volt motion-safe:hover:shadow-glow-cyan',
  secondary: 'glass text-chalk hover:border-white/20 hover:bg-white/5',
  ghost: 'text-ash hover:bg-white/6 hover:text-chalk',
  danger: 'bg-wrong text-chalk hover:opacity-90 motion-safe:hover:shadow-glow-wrong',
}

type ButtonOwnProps<E extends ElementType> = {
  children: ReactNode
  size?: ButtonSize
  variant?: ButtonVariant
  as?: E
  className?: string
}

type ButtonProps<E extends ElementType> = ButtonOwnProps<E> &
  Omit<ComponentPropsWithoutRef<E>, keyof ButtonOwnProps<E>>

export function Button<E extends ElementType = 'button'>({
  children,
  size = 'md',
  variant = 'primary',
  as,
  className = '',
  ...rest
}: ButtonProps<E>) {
  const As = as ?? 'button'
  return (
    <As
      className={`inline-flex items-center justify-center gap-2 rounded-btn font-display font-semibold transition-all duration-150 motion-safe:hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`.trim()}
      {...rest}
    >
      {children}
    </As>
  )
}
