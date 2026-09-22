import { useState } from 'react'
import { Info } from 'lucide-react'
import { RoomCircles } from '../features/play/RoomCircles'
import { SectionHeading } from '../components/SectionHeading'
import { Modal } from '../components/Modal'

/*
 * `/play` — the destination behind the nav's Play button.
 *
 * Public, like the room circles it shows: reading the lobby is free, and
 * tapping a room routes through sign-in via `/play/:room`'s own guard (see
 * router.tsx) rather than gating this page itself.
 *
 * ── The page is the balls ───────────────────────────────────────────────────
 * This used to open with a framed play glyph, a "Play someone" headline and a
 * sentence explaining pairing, and only then the grid. Three blocks of chrome
 * above the one thing the screen is for, on the tab a player opens more than
 * any other — and after the first visit, none of it is read. A lobby in a game
 * is the things you can tap; the explanation is a button, not a paragraph.
 *
 * So what is left above the grid is one label and an `i`. The explanation is
 * not deleted — it moved behind the icon, where the player who wants it can
 * find it every time and the player who doesn't never pays for it again. It is
 * the same trade each room tile already makes with its own `i`
 * (`RoomCircles`), so the page and the tiles in it now say "more about this is
 * one tap away" in one vocabulary.
 *
 * "Pick a room" is the page's `h1`, not a section label under a hidden title:
 * a document that jumps to `h2` has no heading, and the nav's own "Play" is
 * not one — it is a link. `SectionHeading`'s small caps carry it because the
 * balls are the display type on this screen, and a second thing shouting
 * competes with them.
 */
export function PlayIndexPage() {
  const [aboutOpen, setAboutOpen] = useState(false)

  return (
    <div className="flex flex-col gap-5 pb-4">
      <div className="flex items-center gap-2">
        <SectionHeading as="h1">Pick a room</SectionHeading>
        {/* Sized like the tiles' own `i` (h-7 w-7) and styled like it, because
            it is the same promise — this one is about the screen, each of
            those is about one room. */}
        <button
          type="button"
          onClick={() => setAboutOpen(true)}
          aria-label="What is a room?"
          className="flex h-7 w-7 items-center justify-center rounded-full border border-chalk/15 bg-panel/80 text-ash transition-colors hover:border-chalk/30 hover:text-chalk"
        >
          <Info className="h-4 w-4" aria-hidden />
        </button>
      </div>

      <RoomCircles />

      <Modal open={aboutOpen} title="Rooms" onClose={() => setAboutOpen(false)}>
        <div className="flex flex-col gap-3 text-sm leading-relaxed text-ash">
          <p>
            A room is a table you sit at. It sets what the questions are about and how many of them
            you play — tap one and you're in its pool.
          </p>
          <p>
            The next player who joins the same room gets paired with you, and you race: fastest
            correct answer takes the question.
          </p>
          <p>
            Each room's own <span className="text-chalk">i</span> says what is in it. A greyed-out
            room hasn't got enough questions to play right now, and one marked{' '}
            <span className="text-chalk">unrated</span> won't move your rating — rooms that mix
            categories can't, since a rating belongs to one category.
          </p>
        </div>
      </Modal>
    </div>
  )
}
