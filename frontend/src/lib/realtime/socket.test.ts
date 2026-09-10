import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  setAccessTokenGetter,
  setAuthReadyWaiter,
  setTokenRefresher,
} from '../api/session'
import { CLOSE_UNAUTHENTICATED } from './messages'
import { subscribe, type ConnectionState } from './socket'

/*
 * How a socket authenticates, which is the one thing about this layer that has
 * no second chance.
 *
 * The REST client can send a request anonymously, take a 401 and replay it
 * behind a refresh; nobody notices. The socket cannot: an anonymous handshake
 * comes back as a 4401 close, 4401 is a *permanent* code, and a permanent close
 * ends the search or the match outright. So "was the token attached, and was it
 * the current one" is not a detail here — it is the difference between a game
 * and an error screen, and it is worth pinning down rather than trusting to a
 * line in `socketUrl` that nothing would notice the loss of.
 */

/** The last socket handed out, so a test can drive its close handler. */
let last: FakeSocket
const opened: string[] = []

class FakeSocket {
  static readonly OPEN = 1
  readyState = 1
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null

  readonly url: string

  constructor(url: string) {
    this.url = url
    opened.push(url)
    last = this
  }

  send(): void {}
  close(): void {}
}

/** Lets the awaits inside `Connection.open` (auth-ready, then a refresh) run. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

/* Connections are cached module-wide by path and outlive a test, so each test
 * gets a path of its own — sharing one would hand the next test the previous
 * test's connection, including its spent auth retry. */
let pathCounter = 0
const uniquePath = () => `/ws/v1/matches/m-${(pathCounter += 1)}/`

/** What the auth store does on a successful refresh: the new token becomes the
 *  one `getAccessToken` hands out. Without this the reconnect would present the
 *  same token the server just refused, which is the bug, not the fix. */
function refreshesTo(token: string | null) {
  return async () => {
    if (token !== null) setAccessTokenGetter(() => token)
    return token
  }
}

beforeEach(() => {
  opened.length = 0
  vi.stubGlobal('WebSocket', FakeSocket)
  setAuthReadyWaiter(async () => {})
  setAccessTokenGetter(() => 'access-1')
  setTokenRefresher(async () => null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('socket', () => {
  it('puts the access token in the query string', async () => {
    const subscription = subscribe(uniquePath(), () => true, vi.fn(), vi.fn())
    await settle()

    // `?token=` and not a header, because a browser's WebSocket constructor
    // takes none — this is the contract `JWTAuthMiddleware` reads.
    expect(opened).toHaveLength(1)
    expect(opened[0]).toContain('?token=access-1')
    subscription.unsubscribe()
  })

  it('waits for the session before connecting rather than opening anonymously', async () => {
    let releaseSession = () => {}
    setAuthReadyWaiter(() => new Promise<void>((resolve) => (releaseSession = resolve)))
    setAccessTokenGetter(() => 'access-late')

    const subscription = subscribe(uniquePath(), () => true, vi.fn(), vi.fn())
    await settle()
    // A reload has no access token until the bootstrap refresh lands. Opening
    // in that window is not a slow connect, it is a permanent 4401.
    expect(opened).toHaveLength(0)

    releaseSession()
    await settle()
    expect(opened[0]).toContain('token=access-late')
    subscription.unsubscribe()
  })

  it('refreshes once and reconnects when the server refuses the token', async () => {
    setTokenRefresher(refreshesTo('access-2'))
    const states: [ConnectionState, number | undefined][] = []

    const subscription = subscribe(
      uniquePath(),
      () => true,
      vi.fn(),
      (state, code) => states.push([state, code]),
    )
    await settle()

    // An access token that expired mid-match is refusable and refreshable. A
    // player six seconds into a question must not be told to sign in.
    last.onclose?.({ code: CLOSE_UNAUTHENTICATED })
    await settle()

    expect(opened[1]).toContain('token=access-2')
    expect(states.some(([state]) => state === 'closed')).toBe(false)
    subscription.unsubscribe()
  })

  it('gives up when the refresh says the session is over', async () => {
    setTokenRefresher(refreshesTo(null))
    const states: [ConnectionState, number | undefined][] = []

    const subscription = subscribe(
      uniquePath(),
      () => true,
      vi.fn(),
      (state, code) => states.push([state, code]),
    )
    await settle()

    last.onclose?.({ code: CLOSE_UNAUTHENTICATED })
    await settle()

    // Only a null refresh is a logout. The code rides along so the hook above
    // can say "sign in" instead of "reconnecting".
    expect(opened).toHaveLength(1)
    expect(states.at(-1)).toEqual(['closed', CLOSE_UNAUTHENTICATED])
    subscription.unsubscribe()
  })

  it('retries rather than logging out when the refresh cannot reach the server', async () => {
    setTokenRefresher(async () => {
      throw new Error('offline')
    })
    const states: [ConnectionState, number | undefined][] = []

    const subscription = subscribe(
      uniquePath(),
      () => true,
      vi.fn(),
      (state, code) => states.push([state, code]),
    )
    await settle()

    last.onclose?.({ code: CLOSE_UNAUTHENTICATED })
    await settle()

    // A rejected refresh is a network problem, not an expired session — the
    // distinction the auth store draws, kept here too. Ending the match on it
    // would hand the win to whoever's wifi held.
    expect(states.some(([state]) => state === 'closed')).toBe(false)
    subscription.unsubscribe()
  })
})
