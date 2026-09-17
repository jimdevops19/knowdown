import type { ComponentPropsWithoutRef, ElementType, ReactNode } from 'react'

/*
 * The app's action button — a plate of equipment, not a web control.
 *
 * Three things carry that, and all three are deliberate reversals of the
 * default dark-UI button (see index.css for why the default is a problem):
 *
 *  · The primary is a *bright* fill with dark ink on it. An orange bar with dark
 *    lettering is the silhouette of a scoreboard key or a stadium sign; white
 *    text on a saturated mid-tone is the silhouette of every generated app.
 *    It is also the only contrast-safe direction for a colour this light.
 *  · Emphasis on hover is a keyline, not a halo — one crisp pixel of the
 *    button's own colour, the way a broadcast graphic is ruled.
 *  · The label is display type, widened and upper-cased (see the base classes
 *    below). A button here reads as a *call*, in the same voice as the
 *    headings, which is the one place all-caps earns its keep in this app.
 *
 * Motion is gated behind `motion-safe:` so reduced-motion users get a plain
 * colour change. Polymorphic via `as`, so a submit button and a nav link share
 * one look.
 *
 * `full` is not just a width — it is the phone size. A primary action on a
 * phone is a 48px bar across the thumb's reach, and every screen's main verb
 * ("Find a match", "Sign in") uses it below `sm`.
 */
type ButtonSize = 'sm' | 'md' | 'lg' | 'full'
type ButtonVariant = 'primary' | 'accent' | 'secondary' | 'ghost' | 'danger'

// Upper-cased display type needs its letters opened back up — tracking that
// suits a tight headline closes a small caps label into an unreadable block,
// so the tracking loosens as the size drops.
const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs tracking-[0.08em]',
  md: 'h-10 px-4 text-sm tracking-[0.06em]',
  lg: 'h-12 px-6 text-[15px] tracking-[0.05em]',
  full: 'h-12 w-full text-[15px] tracking-[0.05em]',
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  // Dark ink on orange, and it is measured rather than chosen: near-white on
  // this orange is 2.81:1 and fails AA — the pairing LiveScore itself ships,
  // and the one thing from their stylesheet not worth copying. Dark ink on the
  // same fill is 6.89:1.
  primary: 'bg-court text-void hover:bg-deep-court motion-safe:hover:shadow-edge-court',
  // The lit tint of the same orange, for the verb that *starts* something —
  // one step brighter, so a "Ready" reads hotter than a "Save" beside it
  // without introducing a second hue. Same dark-ink rule, same reason.
  accent: 'bg-volt text-void hover:bg-deep-volt motion-safe:hover:shadow-edge-volt',
  secondary: 'plate text-chalk hover:border-chalk/25 hover:bg-raised',
  ghost: 'text-ash hover:bg-chalk/6 hover:text-chalk',
  // Dark ink again, and here it is a fix rather than a flourish: chalk on this
  // red measures 3.1:1, which fails AA for a button label. Dark ink on the same
  // fill is 5.7:1, and it keeps the destructive button in the same family as
  // the other two — every bright plate in this app is read as dark-on-bright.
  danger: 'bg-wrong text-void hover:opacity-90 motion-safe:hover:shadow-edge-wrong',
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
      className={`inline-flex items-center justify-center gap-2 rounded-btn font-display font-bold [font-stretch:var(--display-wide)] uppercase transition-all duration-150 motion-safe:hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`.trim()}
      {...rest}
    >
      {children}
    </As>
  )
}
