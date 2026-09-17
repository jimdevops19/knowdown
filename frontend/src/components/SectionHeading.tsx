import type { ElementType, ReactNode } from 'react'

/*
 * The app's section label — small, uppercase, letter-tracked, muted, and led by
 * a short orange rule.
 *
 * The rule is the whole point of the change. Small caps on their own are a
 * generic label; caps behind a coloured tick are the strap that runs above a
 * segment on a sports broadcast, and because it repeats down every page it is
 * the cheapest possible way to make the app's own vocabulary visible on screens
 * that are otherwise just lists.
 *
 * Caps are used here and on buttons and status chips, and nowhere else — a
 * *label* may shout, a heading may not, which is the line the default look
 * blurs by upper-casing everything small and grey.
 *
 * Centralized so section titles stay consistent and a restyle is a one-file
 * change. Renders an <h2> by default; pass `as="h3"` for a subsection.
 */
export function SectionHeading({
  as: Tag = 'h2',
  className = '',
  children,
}: {
  as?: ElementType
  className?: string
  children: ReactNode
}) {
  return (
    <Tag
      className={`flex items-center gap-2.5 font-display text-xs font-bold [font-stretch:var(--display-wide)] uppercase tracking-[0.16em] text-ash ${className}`.trim()}
    >
      <span aria-hidden className="h-3 w-0.5 shrink-0 bg-court" />
      {children}
    </Tag>
  )
}
