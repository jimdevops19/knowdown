import { Play } from 'lucide-react'
import { CategoryGrid } from '../features/play/CategoryGrid'
import { SectionHeading } from '../components/SectionHeading'

/*
 * `/play` — the destination behind the nav's Play button.
 *
 * Public, like the category cards it shows: picking a category is free to
 * look at, and tapping one routes through sign-in via `/play/:category`'s own
 * guard (see router.tsx) rather than gating this page itself.
 */
export function PlayIndexPage() {
  return (
    <div className="flex flex-col gap-6 pb-4">
      <section className="flex flex-col items-center gap-3 py-4 text-center">
        {/* Orange, not gold: this triangle is the same mark the nav lights, and
            gold is reserved for rank. */}
        <span className="flex h-12 w-12 items-center justify-center rounded-[6px] border border-court/50 bg-court/15 text-court motion-safe:shadow-edge-court">
          <Play size={22} aria-hidden />
        </span>
        <h1 className="font-display text-2xl font-bold text-chalk sm:text-3xl">Play someone</h1>
        <p className="max-w-sm text-balance text-ash">
          Pick a category and you're in the pool — the next matching player gets paired with you.
        </p>
      </section>

      <section className="flex flex-col gap-3">
        <SectionHeading>Pick your category</SectionHeading>
        <CategoryGrid />
      </section>
    </div>
  )
}
