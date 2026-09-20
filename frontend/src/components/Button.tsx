import type { ComponentPropsWithoutRef, ElementType, ReactNode } from 'react'

/*
 * The app's action button — an object you press, not a web control.
 *
 * Four things carry that:
 *
 *  · **It sits on a lip.** Four pixels of its own darker shade underneath, hard
 *    edged, and pressing it drives the button down through that lip until the
 *    lip is gone (`pressable`, index.css). This is the single loudest "this is a
 *    thing, touch it" signal in mobile game UI — Duolingo puts one under every
 *    interactive element — and it costs one shadow token.
 *
 *    What it replaces was `hover:-translate-y-0.5`: a *mouse* affordance, in a
 *    phone-first game. On an actual phone the entire press feedback was a 2%
 *    scale, which is to say there was effectively none, on the control a player
 *    taps a hundred times a match.
 *  · The primary is a *bright* fill with dark ink on it. An orange bar with dark
 *    lettering is the silhouette of a scoreboard key or a stadium sign; white
 *    text on a saturated mid-tone is the silhouette of every generated app.
 *    It is also the only contrast-safe direction for a colour this light.
 *  · Emphasis on a pointer device is a keyline, not a halo — two crisp pixels of
 *    the button's own colour. Hover is a bonus for desktop; the lip is the
 *    affordance that has to work everywhere.
 *  · The label is display type, widened and upper-cased (see the base classes
 *    below). A button here reads as a *call*, in the same voice as the
 *    headings, which is the one place all-caps earns its keep in this app.
 *
 * Polymorphic via `as`, so a submit button and a nav link share one look.
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

/*
 * Every filled variant is <bright fill> + <dark ink> + <its own lip>. The lip
 * colour is always the fill mixed roughly 38% toward black, which is what keeps
 * five different buttons reading as five of the same object rather than as five
 * decisions.
 *
 * `ghost` is the one variant with neither a lip nor the `pressable` utility,
 * and that is the point of it: it has no fill to cast a lip, so 4px of travel
 * would drop its label onto nothing. A flat label beside a lipped button is how
 * a tertiary action stays tertiary without needing to be greyed out. It still
 * answers a tap, with a scale.
 */
const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  // Dark ink on orange, and it is measured rather than chosen: near-white on
  // this orange fails AA outright — the pairing LiveScore itself ships, and the
  // one thing from their stylesheet not worth copying. Dark ink is 6.4:1.
  primary: 'pressable bg-court text-void shadow-lip-court hover:bg-deep-court',
  // The lit tint of the same orange, for the verb that *starts* something —
  // one step brighter, so a "Ready" reads hotter than a "Save" beside it
  // without introducing a second hue. Same dark-ink rule, same reason.
  accent: 'pressable bg-volt text-void shadow-lip-volt hover:bg-deep-volt',
  // A plate rather than a fill, so it takes the plate's own lip: the same 4px
  // of travel, cast by the panel colour instead of by a bright one.
  secondary: 'pressable plate text-chalk shadow-lip-plate hover:border-chalk/30 hover:bg-raised',
  ghost: 'text-ash transition-colors duration-150 hover:bg-chalk/8 hover:text-chalk active:scale-[0.97]',
  // Dark ink again, and here it is a fix rather than a flourish: chalk on this
  // red fails AA for a button label. Dark ink on the same fill is 6.7:1, and it
  // keeps the destructive button in the same family as the other two — every
  // bright plate in this app is read as dark-on-bright.
  danger: 'pressable bg-wrong text-void shadow-lip-wrong hover:opacity-90',
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
      className={`inline-flex items-center justify-center gap-2 rounded-btn font-display font-bold [font-stretch:var(--display-wide)] uppercase disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`.trim()}
      {...rest}
    >
      {children}
    </As>
  )
}
