import type { ReactNode } from 'react'

/*
 * A small data table for compact analytics inside a card — column headers plus
 * tight rows, sized for phone width rather than a dashboard. Not meant for
 * anything paginated or sortable; callers that need that belong to a bigger
 * component, not this one.
 */
export function Table({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`overflow-x-auto ${className}`.trim()}>
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  )
}

export function TableHead({ children }: { children: ReactNode }) {
  return (
    <thead>
      <tr className="border-b border-white/8">{children}</tr>
    </thead>
  )
}

export function TableHeaderCell({
  children,
  align = 'left',
}: {
  children: ReactNode
  align?: 'left' | 'right'
}) {
  return (
    <th
      className={`whitespace-nowrap py-1.5 font-display text-[11px] font-bold uppercase tracking-wider text-ash ${
        align === 'right' ? 'text-right' : 'text-left'
      }`}
    >
      {children}
    </th>
  )
}

export function TableBody({ children }: { children: ReactNode }) {
  return <tbody>{children}</tbody>
}

export function TableRow({ children }: { children: ReactNode }) {
  return <tr className="border-b border-white/5 last:border-0">{children}</tr>
}

export function TableCell({
  children,
  align = 'left',
  className = '',
}: {
  children: ReactNode
  align?: 'left' | 'right'
  className?: string
}) {
  return (
    <td
      className={`whitespace-nowrap py-1.5 text-chalk ${align === 'right' ? 'text-right' : 'text-left'} ${className}`.trim()}
    >
      {children}
    </td>
  )
}
