import type { ElementType, ReactNode } from 'react'

/*
 * The app's section label — small, uppercase, letter-tracked, muted. This exact
 * treatment gets copy-pasted across every panel otherwise; centralizing it
 * keeps section titles consistent and makes a restyle a one-file change.
 * Renders an <h2> by default; pass `as="h3"` for a subsection.
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
      className={`font-display text-xs font-semibold uppercase tracking-[0.14em] text-ash ${className}`.trim()}
    >
      {children}
    </Tag>
  )
}
