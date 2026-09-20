import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { listRooms } from '../../lib/api/endpoints'
import { queryKeys } from '../../lib/query/queryClient'
import { ErrorState } from '../../components/states'
import type { Room } from '../../lib/api/types'

/*
 * The lobby: a grid of rooms, each a disc you tap to join.
 *
 * A room is what a player picks now — the settings a match is played under
 * (which categories, narrowed by which tags, over how many questions) — in
 * place of picking a bare category. Tapping one routes to `/play/:room`, which
 * queues.
 *
 * ── Why discs, and why a grid rather than a rail ────────────────────────────
 * The disc is borrowed from a stories tray, for the reason that shape exists:
 * a ring is a shape people already know to tap, and it stays readable at a size
 * where a card would be a stub. Where it stops being a stories tray is the
 * size, and the scrolling.
 *
 * A stories ring frames a face and truncates its label outside the ring,
 * because the face is the content. A room has no face — its *name* is the
 * content — so the disc is sized to hold the whole name, unclipped, in display
 * type, and the line under it says what is in the room.
 *
 * And the rooms do not sit on a horizontally scrolling rail. A rail is the
 * right shape for a feed of many equal, disposable things; the room list is a
 * short menu of the only choice this app asks a player to make, and a sideways
 * scroll hides half of a short menu behind a gesture phones do not advertise.
 * So: a **two-column grid** on a phone, wrapping down the page, which is the
 * layout every native app uses for a pick-one screen. Wider viewports get more
 * columns, never more than the grid can show at a readable size.
 *
 * Two columns is a hard floor, not a consequence of tile widths: `grid-cols-2`
 * divides whatever width there is, so a 320px phone gets two small discs and a
 * 430px phone two larger ones, and neither can ever fit a third.
 *
  * DESIGN.md reserves round shapes for things that are physically round. This is
 * the deliberate exception the room concept asks for, and it is kept honest by
 * staying inside every *other* rule: never a gradient (the one tell the stories
 * tray would import), and the name inside it is widened display caps like every
 * other display element.
 *
 * ── Why each room is a different colour ─────────────────────────────────────
 * The discs used to be identical: a flat orange keyline on a dark panel,
 * repeated across the grid. That was internally consistent and it made the one
 * genuinely playful choice in the app look like a list of settings — four
 * outlines of the same shape in the same colour is a form, whatever is written
 * inside them.
 *
 * So a room is a solid disc in its own hue, cycled from a set of four by
 * position: the brand orange first, then the three hues whose only job is this
 * (`--color-room-a`/`b`/`c` — violet, pink, lime; see index.css for why those
 * three and not any of the colours already spoken for). Cycled rather than
 * derived from the slug, because a hash would reshuffle every room's colour the
 * day somebody adds a fifth: position is stable, and a player learns "the
 * orange one" from where it sits.
 *
 * Dark ink on the fill, like every other bright surface in the app.
 *
 * Pressing a room drives the disc down through its own lip — the same 4px of
 * travel every button and answer tile now has. That is driven from the <Link>
 * with `group-active:` rather than from the disc's own `:active`, so the whole
 * tap target (disc *and* caption) presses as one object.
 *
 * Hover stays a colour change and nothing else. A lift (`-translate-y`) moves
 * the disc *over* its own description — the two sit a few pixels apart by design
 * — and a transform on a round element next to text reads as a rendering fault
 * rather than as feedback. The press travel is exempt because it goes the other
 * way, into the page, and takes the caption with it.
 *
 * A room that cannot currently fill its own shortest match is rendered, dimmed
 * and unlinked, rather than hidden: `select_room_questions` refuses such a draw
 * server-side, so a player who joined would sit in a queue that could only ever
 * fail — and silently dropping a room from the lobby makes an authoring mistake
 * invisible to the person who made it.
 */
export function RoomCircles() {
  const rooms = useQuery({
    queryKey: queryKeys.rooms.all,
    queryFn: listRooms,
    staleTime: Infinity,
  })

  if (rooms.isLoading) return <RoomGridSkeleton />
  if (rooms.isError) return <ErrorState error={rooms.error} />
  if (!rooms.data) return null
  if (rooms.data.length === 0) {
    return <p className="text-sm text-ash">No rooms are open right now. Check back shortly.</p>
  }

  return (
    <ul className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-4">
      {rooms.data.map((room, index) => (
        <li key={room.slug} className="flex justify-center">
          <RoomCircle room={room} index={index} />
        </li>
      ))}
    </ul>
  )
}

/** The shortest match this room offers — the number of questions it needs in
 *  its pool before it can be played at all. */
function shortestMatch(room: Room): number {
  return room.question_counts.length > 0 ? Math.min(...room.question_counts) : 0
}

/** What the room draws from, in one line, when the author wrote no description.
 *  Named categories are the honest fallback: they are what the filter actually
 *  narrows, and a room with two of them is a thing a player wants to know. */
function contents(room: Room): string {
  if (room.description) return room.description
  if (room.categories.length === 0) return 'No categories yet'
  return room.categories.map((category) => category.name).join(' · ')
}

/* The four fills a room can take, in the order rooms appear. Each carries its
   own lip, so the disc is an object rather than a circle of colour. */
const ROOM_FILLS = [
  'bg-court shadow-lip-court',
  'bg-room-a shadow-lip-room-a',
  'bg-room-b shadow-lip-room-b',
  'bg-room-c shadow-lip-room-c',
] as const

function RoomCircle({ room, index }: { room: Room; index: number }) {
  const playable = room.question_pool_size >= shortestMatch(room)

  const disc = (
    <span
      className={[
        'flex aspect-square w-full max-w-[9rem] items-center justify-center rounded-full px-[8%] text-center transition-[filter,background-color,border-color] duration-150',
        playable
          ? // Solid fill, dark ink, its own lip, and the lip is consumed when the
            // link around it is pressed. Brightness rather than a second fill
            // colour on hover: four hues would otherwise need four hover values,
            // and the disc is already the loudest thing on the screen.
            `text-void group-hover:brightness-110 group-active:translate-y-1 group-active:shadow-none ${ROOM_FILLS[index % ROOM_FILLS.length]}`
          : // An empty room is a plate, not a colour. It cannot be played, and
            // painting it in the same bright fill as a live one would be the
            // lobby's most prominent lie.
            'border-2 border-idle/40 bg-panel text-idle',
      ].join(' ')}
    >
      {/* The whole name, wrapped, not initials and not truncated: the name is
          the only thing that distinguishes one room from the next. Three lines
          is what a disc this size holds at this step; a room named past that
          is an authoring problem, and clamping says so. */}
      <span className="line-clamp-3 font-display text-[clamp(0.8125rem,3.2vw,1rem)] font-bold uppercase leading-[1.15] tracking-[0.04em] [font-stretch:var(--display-wide)]">
        {room.name}
      </span>
    </span>
  )

  // The caption is wider than the disc it sits under: a description reads as a
  // sentence, and a column narrow enough to be a disc's diameter breaks one
  // into a ragged stack of two-word lines.
  const caption = (
    <span className="flex w-full flex-col items-center gap-1">
      <span className="line-clamp-3 text-center text-xs leading-snug text-balance text-ash">
        {contents(room)}
      </span>
      {!playable && (
        <span className="text-[0.625rem] uppercase tracking-[0.1em] text-idle">Empty</span>
      )}
      {/* Said in the lobby, not at the end of the match: a player choosing
          between rooms is choosing whether this game counts, and finding out
          afterwards that their win moved nothing is the version of this that
          feels like a bug. A room mixing categories cannot be scored — see
          `Room.is_rated` — and this is the whole visible consequence. */}
      {playable && !room.is_rated && (
        <span className="text-[0.625rem] uppercase tracking-[0.1em] text-idle">Unrated</span>
      )}
    </span>
  )

  if (!playable) {
    return (
      <div
        className="flex w-full max-w-[11rem] flex-col items-center gap-2 opacity-55 sm:gap-2.5"
        title={`${room.name} has no questions to draw from right now.`}
      >
        {disc}
        {caption}
      </div>
    )
  }

  return (
    <Link
      to={`/play/${room.slug}`}
      className="group flex w-full max-w-[11rem] flex-col items-center gap-2 rounded-card outline-offset-4 sm:gap-2.5"
      aria-label={`Play in ${room.name}${room.is_rated ? '' : ' (unrated)'} — ${contents(room)}`}
    >
      {disc}
      {caption}
    </Link>
  )
}

/** The grid's own shape, so the lobby does not jump a row taller when the real
 *  rooms land. */
function RoomGridSkeleton() {
  return (
    <ul className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-4" aria-hidden>
      {/* Written out rather than composed from <Skeleton>: that component
          carries `rounded-btn`, and two border-radius utilities on one element
          resolve by stylesheet order rather than by the order they are written
          in — a circle that is sometimes a rounded square. */}
      {[0, 1, 2, 3].map((index) => (
        <li key={index} className="flex justify-center">
          <div className="flex w-full max-w-[11rem] flex-col items-center gap-2 sm:gap-2.5">
            <div className="skeleton-fill aspect-square w-full max-w-[9rem] rounded-full bg-chalk/5 motion-safe:animate-skeleton" />
            <div className="skeleton-fill h-3 w-24 rounded-btn bg-chalk/5 motion-safe:animate-skeleton" />
          </div>
        </li>
      ))}
    </ul>
  )
}
