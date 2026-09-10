/*
 * Loading skeletons — a shimmering placeholder block used while data loads,
 * instead of a bare "Loading…" line. `skeleton-fill` (index.css) paints the
 * moving gradient; `animate-skeleton` sweeps it, gated behind motion-safe so
 * reduced-motion users get a still block.
 */
export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={`skeleton-fill motion-safe:animate-skeleton rounded-btn bg-white/5 ${className}`.trim()}
    />
  )
}

/** A stack of skeleton lines; the last is shortened, like real paragraphs. */
export function SkeletonText({ lines = 3, className = '' }: { lines?: number; className?: string }) {
  return (
    <div className={`flex flex-col gap-2 ${className}`.trim()} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={`h-3.5 ${i === lines - 1 ? 'w-2/3' : 'w-full'}`} />
      ))}
    </div>
  )
}

/** A grid of card-shaped skeletons for browse screens. */
export function SkeletonCards({ count = 6, className = '' }: { count?: number; className?: string }) {
  return (
    <div
      className={`grid gap-4 sm:grid-cols-2 lg:grid-cols-3 ${className}`.trim()}
      aria-hidden
      aria-busy="true"
    >
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="glass rounded-card p-5">
          <Skeleton className="mb-4 h-5 w-1/2" />
          <SkeletonText lines={3} />
        </div>
      ))}
    </div>
  )
}

/** Stacked rows, for a ladder or a match history. */
export function SkeletonRows({ count = 8, className = '' }: { count?: number; className?: string }) {
  return (
    <div className={`flex flex-col gap-2 ${className}`.trim()} aria-hidden aria-busy="true">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="glass flex items-center gap-3 rounded-card p-4">
          <Skeleton className="h-10 w-10 rounded-full" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-4 w-12" />
        </div>
      ))}
    </div>
  )
}
