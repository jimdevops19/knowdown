import { Play } from 'lucide-react'
import { RoomCircles } from '../features/play/RoomCircles'
import { SectionHeading } from '../components/SectionHeading'

/*
 * `/play` — the destination behind the nav's Play button.
 *
 * Public, like the room circles it shows: reading the lobby is free, and
 * tapping a room routes through sign-in via `/play/:room`'s own guard (see
 * router.tsx) rather than gating this page itself.
 */
export function PlayIndexPage() {
  return (
    <div className="flex flex-col gap-5 pb-4 sm:gap-6">
      <section className="flex flex-col items-center gap-3 py-1 text-center sm:py-4">
        {/* Orange, not gold: this triangle is the same mark the nav lights, and
            gold is reserved for rank. */}
        <span className="flex h-12 w-12 items-center justify-center rounded-[6px] border border-court/50 bg-court/15 text-court motion-safe:shadow-edge-court">
          <Play size={22} aria-hidden />
        </span>
        <h1 className="font-display text-2xl font-bold text-chalk sm:text-3xl">Play someone</h1>
        <p className="max-w-sm text-balance text-ash">
          Pick a room and you're in its pool — the next player who joins the same room gets paired
          with you.
        </p>
      </section>

      <section className="flex flex-col gap-5">
        <SectionHeading>Pick a room</SectionHeading>
        <RoomCircles />
      </section>
    </div>
  )
}
