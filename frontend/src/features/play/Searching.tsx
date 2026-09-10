import { Radar } from 'lucide-react'
import { Avatar } from '../../components/Avatar'
import { Button } from '../../components/Button'
import { StatusBadge } from '../../components/StatusBadge'

/*
 * Waiting in the pool.
 *
 * The whole screen is one reassurance: *something is happening and it is not
 * stuck*. So there are two independent signs of life — the rings pushing out of
 * the avatar, which say the app is alive, and the elapsed seconds, which say
 * how long it has been. A spinner alone gives neither: a spinner that has been
 * turning for forty seconds looks exactly like one that has been turning for
 * four.
 *
 * The wait has no timeout, and that is deliberate rather than unfinished. The
 * pool is global and a match needs exactly one other person; there is no number
 * of seconds after which "nobody is here" becomes true, only a number after
 * which a player decides to stop — so the decision is theirs, and Cancel is the
 * loudest secondary control on the screen.
 *
 * Cancelling *is* closing the socket (see `useMatchmaking`): the server's
 * disconnect handler frees the slot. There is no request that can fail and
 * leave a phantom waiting in the queue for the next player to be paired with.
 */
export function Searching({
  categoryName,
  displayName,
  avatarUrl,
  playerId,
  waitingSeconds,
  onCancel,
}: {
  categoryName: string
  displayName: string
  avatarUrl: string | null
  playerId: string | null
  waitingSeconds: number
  onCancel: () => void
}) {
  return (
    <div className="mx-auto flex w-full max-w-sm flex-col items-center gap-6 py-8 text-center">
      <StatusBadge tone="live">Finding an opponent</StatusBadge>

      <div className="relative flex h-40 w-40 items-center justify-center">
        {/* Two rings on the same clock, half a period apart, so the pulse is
            continuous rather than a single ping with a gap after it. */}
        {[0, 1].map((index) => (
          <span
            key={index}
            aria-hidden
            className="absolute inset-0 rounded-full border-2 border-volt/50 motion-safe:animate-seek-ping"
            style={{ animationDelay: `${index * 1.1}s` }}
          />
        ))}
        <Avatar name={displayName} seed={playerId ?? displayName} avatarUrl={avatarUrl} size={96} />
      </div>

      <div className="flex flex-col gap-1">
        <h1 className="font-display text-2xl font-bold text-chalk">{categoryName}</h1>
        <p className="flex items-center justify-center gap-2 text-sm text-ash">
          <Radar size={15} className="text-volt" aria-hidden />
          {/* `nums` so the count doesn't shift the line's width every second —
              a wait that jitters reads as less settled than one that doesn't. */}
          <span className="nums">
            Searching · {waitingSeconds}s
          </span>
        </p>
        {waitingSeconds >= 20 && (
          // Only after a while: said immediately it would sound like an excuse
          // for a wait that hasn't happened yet.
          <p className="mt-1 text-xs text-ash/70">
            Quiet right now. You'll be paired the moment someone else queues up.
          </p>
        )}
      </div>

      <Button variant="secondary" size="full" onClick={onCancel}>
        Cancel search
      </Button>
    </div>
  )
}
