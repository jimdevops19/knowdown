/*
 * One WebSocket per subject, reference-counted, with reconnect and a heartbeat.
 *
 * Two things use it: the matchmaking queue and a live matchup. A matchup page
 * mounts several views over one game — the board, the scoreboard, the
 * opponent's presence — and left to themselves each would open its own socket
 * for the same match. So subscriptions are counted here: the first subscriber
 * opens the connection, the last one to leave closes it, everyone in between
 * shares the traffic.
 *
 * The connection is *expected* to fail. Deploys roll the realtime pod, phones
 * go through tunnels, proxies time out. So it reconnects with capped
 * exponential backoff and full jitter, and — the part that is easy to forget —
 * it reports whether it is actually **live**, because in this app a socket that
 * is open but silent is not a stale page, it is a player who cannot answer.
 * That is what the handshake and the silence watchdog below are for.
 *
 * What this module does *not* do is decide what any message means. It moves
 * frames and reports a connection state; `useMatchmaking` and `useMatchup`
 * turn those into a game.
 */

import { getAccessToken, refreshAccessToken, waitForAuthReady } from '../api/session'
import { WS_URL } from '../config'
import {
  CLOSE_UNAUTHENTICATED,
  PERMANENT_CLOSE_CODES,
  PING,
  PONG,
  type ServerMessage,
} from './messages'

/** Sent this often so a proxy doesn't close an idle socket (nginx default: 60s). */
const PING_INTERVAL_MS = 25_000

/**
 * If nothing arrives in this long — not even a pong — the connection is treated
 * as dead and torn down. TCP can hold a half-open socket for many minutes
 * without ever firing an error, which here would look exactly like a question
 * that never opens.
 */
const SILENCE_TIMEOUT_MS = 70_000

const RECONNECT_BASE_MS = 500
const RECONNECT_MAX_MS = 15_000

/**
 * `connecting` — opening, or reconnecting after a drop.
 * `live`       — the server has confirmed the subscription; messages will flow.
 * `closed`     — permanently done with (see PERMANENT_CLOSE_CODES). Nothing is
 *                retried from here; the hook above decides what to show.
 *
 * There is deliberately no `open` state between connecting and live: an open
 * socket the server has not yet acknowledged can deliver nothing, and a UI that
 * treated it as ready would tell a player the match had started before it could
 * receive the first question.
 */
export type ConnectionState = 'connecting' | 'live' | 'closed'

type Listener = (message: ServerMessage) => void
type StateListener = (state: ConnectionState, closeCode?: number) => void

/**
 * Where to connect, **with the access token in the query string**.
 *
 * Not a choice either side made freely: a browser's `WebSocket` constructor
 * accepts no headers, so the `Authorization: Bearer` the REST client uses is
 * not available here, and `?token=` is the contract the backend settled on
 * (`apps.matches.authentication.JWTAuthMiddleware`). The cost is that the token
 * can land in a proxy access log, which is why the backend redacts query
 * strings — worth knowing before this pattern is copied to anything else.
 *
 * Built fresh on every connect rather than once per `Connection`: an access
 * token is short-lived, and a socket reconnecting twenty minutes into a session
 * must present the token the session holds *now*, not the one it opened with.
 */
function socketUrl(path: string, token: string | null): string {
  const origin = WS_URL
    ? WS_URL.replace(/\/$/, '')
    : // Same origin as the page, with the scheme derived from it rather than
      // configured: an https page must never be talked into an insecure socket
      // by way of a stale env var.
      `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
  return token ? `${origin}${path}?token=${encodeURIComponent(token)}` : `${origin}${path}`
}

class Connection {
  private socket: WebSocket | null = null
  private readonly listeners = new Set<Listener>()
  private readonly stateListeners = new Set<StateListener>()
  private state: ConnectionState = 'connecting'
  private lastCloseCode: number | undefined
  private attempt = 0
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private silenceTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  /** Set when the server says this subject can never be reached — stop retrying. */
  private abandoned = false
  /** Whether the one refresh-and-retry a 4401 is allowed has been spent. */
  private retriedAuth = false
  /** Set once the last subscriber let go. Distinct from `listeners.size === 0`,
   *  which is also true for the instant between `new Connection` and the first
   *  `subscribe` — a window `open`'s await now falls inside. */
  private released = false

  private readonly path: string
  /** How this connection recognises the server's "you are subscribed" message.
   *  Passed in because the two sockets spell it differently — `searching` on
   *  the queue, `question.started` on a matchup — and treating a bare `open` as
   *  live is the one failure mode that must not read as healthy. */
  private readonly isHandshake: (message: ServerMessage) => boolean
  private readonly onEmpty: () => void

  constructor(path: string, isHandshake: (message: ServerMessage) => boolean, onEmpty: () => void) {
    this.path = path
    this.isHandshake = isHandshake
    this.onEmpty = onEmpty
    void this.open()
  }

  subscribe(onMessage: Listener, onState: StateListener): () => void {
    this.listeners.add(onMessage)
    this.stateListeners.add(onState)
    onState(this.state, this.lastCloseCode)
    return () => {
      this.listeners.delete(onMessage)
      this.stateListeners.delete(onState)
      if (this.listeners.size === 0) this.close()
    }
  }

  /** Send one frame, if there is an open socket to send it on.
   *
   *  Returns whether it went out, and does **not** queue on failure. A queued
   *  answer is worse than a dropped one: it would arrive after the reconnect,
   *  against a question that has since closed, and be refused — while the
   *  player, who saw their tile light up, believes they answered in time. */
  send(message: object): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false
    this.socket.send(JSON.stringify(message))
    return true
  }

  private setState(state: ConnectionState, closeCode?: number): void {
    // Not short-circuited on an unchanged state: a reconnect that lands back on
    // `live` is news even though the value is the same as before the drop, and
    // the hooks above use that edge to resync.
    this.state = state
    this.lastCloseCode = closeCode
    for (const listener of this.stateListeners) listener(state, closeCode)
  }

  private async open(): Promise<void> {
    if (this.abandoned) return

    // Hold the connect until the session is settled. Only the access token is
    // in memory, so a reload starts with none and has to refresh for one; a
    // socket that opened during that window would arrive anonymous and be
    // closed 4401 — permanently, since there is no reconnect from a permanent
    // code. This is the socket's counterpart to the REST client's `authReady`
    // gate, and it matters more here: REST replays a 401, a socket cannot.
    await waitForAuthReady()
    // Re-checked after the await: the last subscriber may have let go while we
    // waited, and opening a socket for a page that has already unmounted would
    // leave one nobody closes.
    if (this.abandoned || this.released) return

    const socket = new WebSocket(socketUrl(this.path, getAccessToken()))
    this.socket = socket

    socket.onopen = () => {
      // Deliberately *not* `live` yet — see ConnectionState. The server
      // confirms the subscription with its own first message; until then this
      // socket can deliver nothing.
      this.startHeartbeat()
    }

    socket.onmessage = (event) => {
      this.noteTraffic()
      let message: ServerMessage
      try {
        message = JSON.parse(event.data as string) as ServerMessage
      } catch {
        return
      }
      if (message.type === PONG) return
      if (this.state !== 'live' && this.isHandshake(message)) {
        this.attempt = 0
        // A connection that reached `live` proved the token it presented was
        // good, so the next expiry — twenty minutes into a long session — gets
        // its own retry rather than inheriting a spent one.
        this.retriedAuth = false
        this.setState('live')
      }
      // The handshake message is forwarded as well as promoting the state: on a
      // matchup socket it *is* the question in progress, and swallowing it
      // would leave a reconnecting player looking at an empty board.
      for (const listener of this.listeners) listener(message)
    }

    socket.onclose = (event) => {
      this.stopHeartbeat()
      // A 4401 is permanent in the protocol but not always in fact: an access
      // token that expired mid-match is refusable and refreshable, and a player
      // six seconds into a question should not be told to sign in. So it gets
      // exactly one refresh-and-retry — once, tracked on the connection, or a
      // server that refuses every token would spin here forever.
      if (event.code === CLOSE_UNAUTHENTICATED && !this.retriedAuth) {
        this.retriedAuth = true
        this.setState('connecting', event.code)
        void this.reopenWithFreshToken()
        return
      }
      if (PERMANENT_CLOSE_CODES.includes(event.code)) {
        this.abandoned = true
        this.setState('closed', event.code)
        return
      }
      this.setState('connecting', event.code)
      this.scheduleReconnect()
    }

    socket.onerror = () => {
      // `onclose` always follows and it carries the code, so the reconnect
      // logic lives there and runs exactly once per failure.
    }
  }

  /** The one retry a 4401 gets. See its call site in `onclose`. */
  private async reopenWithFreshToken(): Promise<void> {
    let token: string | null
    try {
      token = await refreshAccessToken()
    } catch {
      // The refresh could not reach the server — which is a network problem,
      // not an expired session. Treat it as the transport failure it is and let
      // the ordinary backoff have it, rather than logging anybody out.
      this.scheduleReconnect()
      return
    }
    if (token === null) {
      // The server says the session is over. This one really is permanent, and
      // the code is what tells the hook above to say "sign in" rather than
      // "reconnecting".
      this.abandoned = true
      this.setState('closed', CLOSE_UNAUTHENTICATED)
      return
    }
    void this.open()
  }

  private scheduleReconnect(): void {
    if (this.abandoned || this.listeners.size === 0) return
    // Full jitter: without it, every client of a realtime pod that just rolled
    // comes back in the same millisecond and knocks the new one over on
    // arrival. Backoff is faster than a dashboard's would be — a player mid
    // match is waiting on this, so the first retry is half a second.
    const ceiling = Math.min(RECONNECT_BASE_MS * 2 ** this.attempt, RECONNECT_MAX_MS)
    this.attempt += 1
    this.reconnectTimer = setTimeout(() => void this.open(), Math.random() * ceiling)
  }

  private startHeartbeat(): void {
    this.stopHeartbeat()
    this.pingTimer = setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify({ type: PING }))
      }
    }, PING_INTERVAL_MS)
    this.noteTraffic()
  }

  private noteTraffic(): void {
    if (this.silenceTimer) clearTimeout(this.silenceTimer)
    this.silenceTimer = setTimeout(() => {
      // Over a minute with nothing, not even a pong. Close it ourselves so the
      // reconnect path runs: a half-open socket never fires `onclose` on its
      // own, and the page would sit there looking live and receiving nothing.
      this.socket?.close()
    }, SILENCE_TIMEOUT_MS)
  }

  private stopHeartbeat(): void {
    if (this.pingTimer) clearInterval(this.pingTimer)
    if (this.silenceTimer) clearTimeout(this.silenceTimer)
    this.pingTimer = null
    this.silenceTimer = null
  }

  private close(): void {
    this.released = true
    this.stopHeartbeat()
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    // Drop the handlers before closing: `onclose` would otherwise queue a
    // reconnect for a connection nobody is watching any more.
    if (this.socket) {
      this.socket.onclose = null
      this.socket.onmessage = null
      this.socket.onopen = null
      this.socket.onerror = null
      this.socket.close()
      this.socket = null
    }
    this.onEmpty()
  }
}

const connections = new Map<string, Connection>()

/** A handle on one shared connection, handed back by {@link subscribe}. */
export interface Subscription {
  /** Stop listening. The connection closes when the last subscriber lets go. */
  unsubscribe: () => void
  /** Send a frame. False when there was no open socket to send it on. */
  send: (message: object) => boolean
}

/**
 * Watch one subject, sharing a socket with anyone else already watching it.
 *
 * @param path        the ws path, e.g. `/ws/v1/matches/{id}/`
 * @param isHandshake recognises the server message that proves the
 *                    subscription is live — see `Connection.isHandshake`
 */
export function subscribe(
  path: string,
  isHandshake: (message: ServerMessage) => boolean,
  onMessage: Listener,
  onState: StateListener,
): Subscription {
  let connection = connections.get(path)
  if (!connection) {
    connection = new Connection(path, isHandshake, () => connections.delete(path))
    connections.set(path, connection)
  }
  const held = connection
  return {
    unsubscribe: held.subscribe(onMessage, onState),
    send: (message: object) => held.send(message),
  }
}
