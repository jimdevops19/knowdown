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
        <span className="flex h-12 w-12 items-center justify-center rounded-full border border-gold/50 bg-gold/15 text-gold motion-safe:shadow-glow-gold">
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
