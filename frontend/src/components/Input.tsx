import type { ComponentPropsWithRef } from 'react'

/*
 * The standard form input surface — a raised field with a cyan focus ring.
 * Centralizes the class string rather than repeating it across every form.
 *
 * 44px minimum height even at `sm`: below that a field is under the tap target
 * every mobile accessibility guideline asks for, and this app is a phone app
 * first.
 */
// `WithRef`, not `WithoutRef`: React 19 passes `ref` as an ordinary prop to a
// function component, and the free-text board needs one to focus the field the
// moment a question opens. `size` is omitted because the native attribute is a
// character count for text inputs, and our token has to win.
type InputProps = Omit<ComponentPropsWithRef<'input'>, 'size'> & {
  size?: 'sm' | 'md'
  /** Paints the error state. The message itself belongs to <Field>. */
  invalid?: boolean
}

const SIZE_HEIGHT: Record<'sm' | 'md', string> = {
  sm: 'h-11 text-sm',
  md: 'h-12',
}

export function Input({ size = 'md', invalid = false, className = '', ...rest }: InputProps) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={`w-full rounded-input border bg-raised px-3.5 text-chalk outline-none transition-all duration-150 placeholder:text-ash/50 focus:ring-2 disabled:opacity-60 ${
        invalid
          ? 'border-wrong/60 focus:border-wrong focus:ring-wrong/25'
          : 'border-white/8 focus:border-volt focus:ring-volt/25'
      } ${SIZE_HEIGHT[size]} ${className}`.trim()}
      {...rest}
    />
  )
}
