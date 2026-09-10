import { useEffect, useRef, useState } from 'react'
import {
  MATCH_FOUND,
  SEARCHING,
  SEARCH_CANCEL,
  CLOSE_NOT_FOUND,
  CLOSE_POOL_BUSY,
  CLOSE_RATE_LIMITED,
  CLOSE_UNAUTHENTICATED,
  type ServerMessage,
} from './messages'
import { subscribe, type ConnectionState } from './socket'

/*
 * Sitting in a category's matchmaking pool until somebody else does too.
 *
 * The whole feature is "hold a socket open and wait", which is exactly why it
 * is worth a hook of its own: the *lifetime* of that socket is the feature.
 * Connecting joins the pool; disconnecting leaves it. There is no "leave"
 * request to send and no cleanup to remember, because the server's `disconnect`
 * handler is what removes the player from the queue — so a closed laptop, a
 * killed tab and a tapped Cancel all leave the pool the same way, and none of
 * them can strand a phantom opponent in it for the next player to be paired
 * with.
 *
 * That inverts the usual rule about effects: here, tearing the effect down is
 * not cleanup, it is the cancel.
 */

export type MatchmakingPhase =
  /** Opening the socket — the server hasn't confirmed the queue yet. */
  | 'connecting'
  /** In the pool. The server said so; this is not a guess from `onopen`. */
  | 'searching'
  /** Paired. `matchupId` is set and the caller should navigate to the match. */
  | 'found'
  /** Not signed in, no such category, or the pool refused the join. */
  | 'failed'

export interface Matchmaking {
  phase: MatchmakingPhase
  /** Set exactly when `phase === 'found'`. */
  matchupId: string | null
  /** Why it failed, in words a player can act on. Null unless `failed`. */
  error: string | null
  /** How long the search has been running, in whole seconds — for the "still
   *  looking…" copy that makes a wait feel attended to rather than hung. */
  waitingSeconds: number
  /** Give up. Closes the socket, which *is* leaving the pool. */
  cancel: () => void
}

/** Reasons a search ends without a match, keyed by the close code the server
 *  used. Anything else is a transport failure, which reconnects rather than
 *  failing — so it never reaches this table. */
const CLOSE_REASONS: Record<number, string> = {
  [CLOSE_UNAUTHENTICATED]: 'Sign in to play a ranked match.',
  [CLOSE_POOL_BUSY]: 'Matchmaking is busy right now. Try again in a moment.',
  // The category slug in the URL isn't one the server knows — a stale link, a
  // typo, or a category that has since been deactivated. Left out of this table
  // it fell through to "ended unexpectedly", which is the one thing it is not:
  // it will fail identically forever, so the copy has to point somewhere else.
  [CLOSE_NOT_FOUND]: "That category isn't available. Pick another from the home screen.",
  // Not "slow down" — the limit counts sockets held open as well as joins, and
  // the usual way to hit it is a second tab still sitting in the queue.
  [CLOSE_RATE_LIMITED]: 'Too many searches at once. Close any other tab you have open and retry.',
}

/**
 * Join `category`'s pool and wait to be paired.
 *
 * @param categorySlug the category to queue in, or null to queue in nothing —
 *        which is how a caller keeps this hook mounted (rules of hooks) while
 *        the player is still choosing.
 */
export function useMatchmaking(categorySlug: string | null): Matchmaking {
  const [phase, setPhase] = useState<MatchmakingPhase>('connecting')
  const [matchupId, setMatchupId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [waitingSeconds, setWaitingSeconds] = useState(0)
  const cancelRef = useRef<() => void>(() => {})

  useEffect(() => {
    if (!categorySlug) return
    setPhase('connecting')
    setMatchupId(null)
    setError(null)
    setWaitingSeconds(0)

    // The pairing may arrive on the very first frame, before `searching` ever
    // does — the server pairs inside `connect` when somebody is already
    // waiting. So `match.found` counts as the handshake too, or a socket that
    // matched instantly would never be marked live.
    const isHandshake = (message: ServerMessage) =>
      message.type === SEARCHING || message.type === MATCH_FOUND

    const onMessage = (message: ServerMessage) => {
      if (message.type === SEARCHING) {
        setPhase('searching')
      } else if (message.type === MATCH_FOUND) {
        // Set before the phase, so a caller reading both in the same commit
        // never sees `found` with a null id.
        setMatchupId(message.matchup_id)
        setPhase('found')
      }
    }

    const onState = (state: ConnectionState, closeCode?: number) => {
      if (state !== 'closed') return
      // A permanent close. `CLOSE_MATCHED` is the *good* one — it follows
      // `match.found` immediately, and the phase is already 'found', so
      // treating every permanent close as a failure would flip a successful
      // pairing into an error a few milliseconds after it succeeded.
      setPhase((current) => {
        if (current === 'found') return current
        setError(CLOSE_REASONS[closeCode ?? -1] ?? 'The search ended unexpectedly.')
        return 'failed'
      })
    }

    const subscription = subscribe(
      `/ws/v1/matchmaking/${categorySlug}/`,
      isHandshake,
      onMessage,
      onState,
    )

    cancelRef.current = () => {
      // Best-effort courtesy: it lets the server free the slot now rather than
      // on the close it is about to see anyway. The unsubscribe below is what
      // actually leaves the pool, so this failing costs nothing.
      subscription.send({ type: SEARCH_CANCEL })
      subscription.unsubscribe()
    }

    return () => {
      cancelRef.current = () => {}
      subscription.unsubscribe()
    }
  }, [categorySlug])

  // The visible wait. Counted from when this hook started searching rather than
  // from a server timestamp, because nothing about it is scored — it is here to
  // reassure, and a second of drift costs nobody anything.
  useEffect(() => {
    if (phase !== 'searching') return
    const id = setInterval(() => setWaitingSeconds((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [phase])

  return {
    phase,
    matchupId,
    error,
    waitingSeconds,
    cancel: () => cancelRef.current(),
  }
}
