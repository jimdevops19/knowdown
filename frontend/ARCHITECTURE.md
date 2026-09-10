# knowdown Frontend — Design & Architecture

The blueprint the React SPA is built against: the backend contract, the realtime
protocol, the routing, and the handful of decisions that everything else follows
from.

> Read `backend/CLAUDE.md` alongside this. The backend is Django 6 + DRF,
> HackSoft-layered (views → selectors/services), JWT + Google OAuth, JSON under
> `/api/v1/`, with the live game over Channels at `/ws/v1/`. Interactive API
> docs are at `/api/docs/` — **development only**.

---

## 1. What the app is

One thing: get paired with a stranger and race them through 3, 5 or 7 trivia
questions at ten seconds each. Everything else on the screen exists to explain
that, get you into it, or show you what happened afterwards.

There is one persona — a **player** — and no admin surface. That is a real
simplification over a tournament app: there is no organizer, no operator, no
private-vs-public scoping question, and no screen where one person acts on
another's behalf. Every screen is either "you", "somebody public", or "a match
you were in".

**Phone first, and meant literally.** The single most important screen is a
ten-second question board held one-handed. Every layout decision downstream of
that — 56px answer tiles, a page that does not scroll, `touch-action:
manipulation` to kill the 300ms tap delay, a nav that switches on viewport
*shape* rather than width — comes from it.

---

## 2. The one decision everything else follows from

**The socket carries the game. REST carries everything else.**

A realtime layer that only says "match {id} changed, go refetch" is right when
the REST endpoint is the source of truth and the socket merely decides *when* to
ask. It is wrong here, and the reason is the clock: the server stamps a question
when it opens, closes it ten seconds later, and scores the response time against
that stamp. A round trip to ask "what is the question?" would be the exact
latency the game is measuring.

So `question.started` carries the whole board, and `lib/api/endpoints.ts`
contains no function that plays anything.

The rule that replaces "keep messages thin" is:

> **Nothing that crosses the socket while a clock is running may identify a
> correct answer.**

Which is the same rule the backend's play-time serializers enforce, from the
other side. See §5.

---

## 3. Backend contract

### 3.1 Base URL and versioning

Everything is under **`/api/v1/`**; the sockets are under **`/ws/v1/`**. Both
prefixes are single seams, kept in one config constant each.

Dev: the Vite proxy forwards `/api`, `/ws` and `/media` to
`http://127.0.0.1:8000`, so every call is same-origin from the browser's point
of view and there is no CORS to configure. Production: nginx does the same
split, but to two deployments of one image — gunicorn for `/api/`, uvicorn
(`config.asgi`) for `/ws/` — so a spectator holding a socket open cannot occupy
a worker that is answering REST calls.

### 3.2 Envelopes

Success:

```jsonc
{ "data": <payload> }
```

Lists add a sibling `meta`:

```jsonc
{ "data": [ ... ], "meta": { "pagination": {
  "count": 137, "page": 2, "pages": 6, "page_size": 25,
  "next": "…", "previous": "…"
} } }
```

`lib/api/client.ts` unwraps `.data` centrally and hangs `meta` off the response,
so no component ever sees the envelope.

Errors are normalized to:

```jsonc
{ "error": { "code": "validation_failed", "message": "…",
             "details": { "field": ["…"] }, "request_id": "…" } }
```

→ a typed `ApiError { code, message, details, requestId, status }`. **The socket
uses the same shape** (`events.ERROR` carries a `code`/`message` pair
deliberately identical to a REST 4xx), so one error model serves both
transports — see `apiErrorFromSocket`.

### 3.3 Auth

- **JWT.** The access token is in memory only, never persisted.
- **The refresh token is not client state at all.** It lives in an HttpOnly
  cookie scoped to the auth routes; JS never sees its value. A week-long,
  self-rotating credential in `localStorage` is one XSS away from a silent,
  permanent account takeover.
- On 401 → a single-flight refresh → retry once → else clear and redirect.
- **A backend that cannot be reached is not a session that has ended.** A
  refresh the server *rejects* logs out; one that never reached a server is
  retried and then thrown, so a deploy rolling the API pods does not read as a
  mass logout.

#### Requests wait for the session

A reload starts with no access token and no client-visible signal of whether a
refresh cookie exists, so every cold load must ask the server once. Any request
sent before that answer goes out anonymous — and on a scoped endpoint that is
*terminal*: `/matches/{id}/` answers **403**, which `client.ts` does not replay
(it only replays 401) and `queryClient.ts` refuses to retry (no 4xx is
retried). The page would show "not yours" to the person whose match it is until
they reloaded, and auth arriving a moment later would change nothing because the
query key never changed.

So the request interceptor `await`s `authReady()`. It lives in the client rather
than as `enabled: status !== 'loading'` on each query, because the per-query
version has to be remembered on every scoped fetch on every page and fails
**silently** when forgotten. Credential-exchange calls skip the wait — queueing
the bootstrap refresh behind itself would deadlock.

### 3.4 Endpoint catalog

🔓 = `AllowAny`, 🔒 = JWT.

| Method | Path | Notes |
|---|---|---|
| POST 🔓 | `auth/token/` | Sign in. **Email and password only** — the display name is published on every ladder row, so it is no part of a credential. |
| POST 🔓 | `auth/token/refresh/` | No body; the cookie is the credential. |
| POST 🔓 | `auth/registration/` | `{email, password1, password2}` → a signed-in session. No display name. |
| POST 🔓 | `auth/google/` | `{access_token}` → knowdown JWTs. |
| POST 🔓 | `auth/logout/` | Blacklists the refresh token, unsets the cookie. |
| POST 🔓 | `auth/password/reset/`, `…/confirm/` | Own throttle scope. |
| GET 🔓 | `auth/config/` | `{password_enabled, google_enabled}` — **asked before the sign-in screen draws**. |
| GET/PATCH 🔒 | `auth/me/` | **The only endpoint in the API that may emit an email address.** |
| GET 🔓 | `categories/`, `categories/{slug}/` | |
| GET/PATCH 🔒 | `players/me/` | Name and avatar. PATCH routes to services, not to a serializer `update`. |
| GET 🔒 | `players/display-name-available/` | Authenticated, so it isn't a name-enumeration oracle. |
| GET 🔓 | `players/{display_name}/` | Public profile: ratings + badges, one round trip. Case-insensitive. |
| GET 🔓 | `rankings/{category}/` | Paginated ladder. |
| GET 🔒 | `matches/` | Your own history, newest first. |
| GET 🔒 | `matches/{id}/` | Full box score, scoped to its two players. **See §7.** |

#### Auth realities the UI is shaped around

- **Sign-in is not an account-existence oracle.** A wrong password, an unknown
  address and a malformed one are refused *identically*, and an unknown address
  is hashed against anyway so it cannot be told apart by timing. `LoginPage`
  therefore shows exactly **one** error line covering both fields. `RegisterPage`
  does show per-field errors, because there is no oracle left to protect.
- **A tier without password auth leaves those routes unmounted** (404, not 403).
  A form posting into a 404 fails with nothing useful to say, which is why
  `useAuthConfig` is consulted first.
- **Signing up is two screens.** The account arrives with a generated name
  (`player_7`, flagged `player_name_is_auto`) that is **never** derived from the
  email — that name goes on every scoreboard. `/welcome` is where a person
  replaces it, and nothing is blocked behind doing so.
- **The Google button needs both halves**: server credentials (`google_enabled`)
  *and* a client id. Either missing is a button that fails on tap.

---

## 4. The realtime protocol

Two sockets, both under `/ws/v1/`, both authenticated by JWT.

### 4.0 How a socket authenticates

**The token goes in the query string: `/ws/v1/…/?token=<access token>`.** Not a
preference — a browser's `WebSocket` constructor accepts no headers, so the
`Authorization: Bearer` every REST call uses is simply unavailable, and
`?token=` is the contract `apps.matches.authentication.JWTAuthMiddleware`
reads. The cost is that the token can land in a proxy access log, which is why
the backend redacts query strings; know that before copying the pattern
anywhere else.

Three consequences the socket layer has to carry, none of which REST does:

- **It waits for the session.** Only the access token is in memory, so a reload
  starts with none and has to refresh for one. A REST call that goes out in
  that window takes a 401 and is replayed; a socket that does takes a **4401
  close, which is permanent**, and the player is told to sign in while signed
  in. `Connection.open` awaits `waitForAuthReady()` first, for the same reason
  the axios request interceptor does — but where that is a convenience, this is
  the difference between a game and an error screen.
- **It re-reads the token on every connect.** The URL is rebuilt inside `open`,
  not cached on the `Connection`, so a socket reconnecting twenty minutes in
  presents the token the session holds *now*.
- **A 4401 gets exactly one refresh-and-retry.** An access token that expired
  mid-question is refusable and refreshable, and a player six seconds into a
  clock should not be signed out over it. Once per connection, and reset only
  after a connection has proved a token good by reaching `live`. A refresh that
  *rejects* is a network problem, not an expired session — it backs off and
  retries rather than logging anybody out, the same distinction the auth store
  draws.

`socket.test.ts` pins all four behaviours, because losing the token from the
URL is a one-line regression that nothing else would notice.

### 4.1 `matchmaking/{category}/`

Connecting joins the pool; **disconnecting leaves it**. There is no leave
request — the server's `disconnect` handler frees the slot, so a closed laptop,
a killed tab and a tapped Cancel all behave identically and none can strand a
phantom in the queue.

```
→ searching                    the handshake; you are in the pool
→ match.found { matchup_id }    followed immediately by close 4200
← search.cancel                 a courtesy; closing is what matters
```

### 4.2 `matches/{matchup_id}/`

```
→ question.started { order, question }    the whole board. no answer in it.
→ player.answered  { order, player_id }   WHO, never what or whether
→ question.result  { order, results[] }   the one message carrying a verdict
→ match.completed  { outcome, winner_player_id, scores }
→ opponent.disconnected / opponent.reconnected
→ error { code, message }
← answer.submit { order, payload }        the only write a client may make
```

**There is no separate "connected" frame.** The handshake *is* the first
`question.started` — being subscribed and having a board are the same event
here, which is also what makes a reconnect a resume: the server re-sends the
question in progress.

**`match.completed` is authoritative.** It replaces whatever the client
accumulated, which is what rescues a client that missed half the match to a bad
tunnel.

### 4.3 The client half — `lib/realtime/`

- **`socket.ts`** — one connection per subject, reference-counted, with capped
  exponential backoff and **full jitter** (without it, every client of a pod
  that just rolled reconnects in the same millisecond). A 25s ping and a 70s
  silence watchdog catch half-open connections that never fire `onclose`.
  Permanent close codes (4401, 4404, 4200, 4429) stop the retry loop. 4429 is
  the counter-intuitive member: the connection was refused *because* this client
  has been connecting too much (`apps.matches.abuse`), so backing off would
  still be reconnecting — the player retries by hand.
- **`useMatchup.ts`** — the state machine, as a **reducer**. Events arrive in
  bursts (a result, the next question and sometimes the final summary in one
  tick), and every transition must apply in order from the previous state with
  no stale closure between. Fully unit-tested with the socket mocked to two
  callbacks.
- **`useMatchmaking.ts`** — the pool, where the effect's *lifetime* is the
  feature.

**The client is never the referee.** `useQuestionClock` draws the server's ten
seconds; it does not enforce them. When it hits zero the board stops taking taps
— that is all — and the question genuinely closes when a `question.result`
arrives. A client whose clock ran fast would only disadvantage its own player.

**An in-flight answer is never queued.** A send that fails is not an answer: it
would arrive after the reconnect, against a question that has since closed, and
be refused — while the player, who watched their tile light up, believed they
answered in time.

**No polling fallback, deliberately.** In an app whose socket messages are thin
pointers, polling is a genuine fallback because the REST endpoint is the real
source. Here the socket *is* the source; there is nothing to fall back to, so a
dropped socket is a reconnect and the server answers it by re-sending the
question in progress.

---

## 5. The anti-cheat surface

The backend calls `apps/questions/api/serializers.py` "the anti-cheat surface"
and defends it structurally: a play-time serializer that declares `is_correct`,
`answer`, `correct_position` or `accepted_answers` raises at **import**, so the
app refuses to boot rather than booting and leaking.

What that means on this side:

1. **`PlayQuestion` has no answer field**, because the payload has none. A
   client author looking for "how many options are correct" or "which one was
   right" will not find them; both are documented as deliberate absences in
   `lib/api/types.ts`.
2. **Options arrive shuffled per matchup** — the same order for both players
   (a race over different boards is not a race), a different order in a later
   match. For ordering questions this is not cosmetic: the authored order *is*
   the answer.
3. **`question.result` says whether *you* were right, and never publishes the
   key.** The same question can come up again in someone else's match. So no
   board reveals "the correct option" and the box score doesn't either.
4. **`QuestionBoard.test.tsx` proves the boards render only what they name.** It
   feeds every board a payload deliberately poisoned with the forbidden fields —
   as though a regression upstream had started sending them — and asserts none
   reaches `innerHTML` (not `textContent`: an answer in a `title` or `data-`
   attribute is just as readable in devtools). What it establishes is that there
   is no `{...option}` spread and no "render whatever keys came back" loop
   anywhere, so a leak upstream stays upstream.

---

## 6. Routing

| Route | Access | Screen |
|---|---|---|
| `/` | 🔓 | Category picker + the way in. Signed in, your standings below it. |
| `/how-to-play` | 🔓 | The rules. |
| `/rankings`, `/rankings/:category` | 🔓 | The ladder. |
| `/players/:displayName` | 🔓 | Public profile: ratings, badges. |
| `/play/:category` | 🔒 | Matchmaking. Mount = queue; leave = cancel. |
| `/match/:id` | 🔒 | **The live game.** |
| `/matches` | 🔒 | Your history. |
| `/matches/:id` | 🔒 | The box score. |
| `/me` | 🔒 | Name, picture, sign-in email. |
| `/login`, `/register`, `/welcome`, `/forgot-password`, `/reset-password` | — | Standalone `AuthLayout`. |

**Public where it can be.** The home page, the ladder, any profile and the rules
are all open: they are the answer to "what would I be signing up for", and they
cannot sit behind signing up. The category cards route *through* the guard
rather than hiding, and `RequireAuth` carries the destination in `?next=` so a
link into a live match survives the detour.

**`/match/:id` and `/matches/:id` are deliberately different segments.** One
rejoins a socket, the other reads a finished game. Collapsing them would mean
guessing which the player wanted from a status that may have changed since the
link was made.

---

## 7. Known gap: the box score is fetchable mid-match

`GET /matches/{id}/` serializes **every** `MatchupQuestion` of the matchup, and
`selectors.list_matchups_for_player` applies no status filter — so calling it on
an **active** match returns the boards of questions that have not been asked
yet, through the same play-time serializer, to a player who is currently racing
them.

The client refuses to use it during play: the roster fetch is deferred to
`MatchSummary`, which only mounts once the match is terminal. The visible cost
is that the live scoreboard says **"Rival"** rather than a name — the socket
sends player ids and nothing else, and this is the only endpoint that would
resolve them. `Avatar`'s `seed` colours the opponent from their id so they read
as a specific someone rather than a blank.

That is a workaround, not a fix. The fix belongs on the backend, and is either
of:

- scope `MatchHistoryDetailView` to terminal matchups (a live match is not
  history), or
- give `MatchupDetailSerializer` a live mode that emits only `started_at`-
  stamped questions, and add a light roster endpoint the live screen can call.

Until then, treat "do not fetch a match detail while it is live" as a rule of
this codebase, not a preference.

---

## 8. Data layer

- **Query keys** live in one place (`lib/query/queryClient.ts`), so an
  invalidation and the query it means to invalidate cannot drift.
- **`keepPreviousData`** on paged lists: on a phone, collapsing a list to a
  skeleton and back moves the page under a thumb that is already reaching.
- **The end of a match invalidates** its box score, the history list and the
  ladder — the three things it just changed.
- **4xx is never retried**; transient errors are, up to twice.

---

## 9. Design system

Dark only. Every token is in `src/index.css`; a restyle is one file.

| Token | Value | Means |
|---|---|---|
| `court` | `#7C3AED` | primary — buttons, active, **your** side |
| `volt` | `#22D3EE` | accent — live, the clock, links, focus |
| `gold` | `#FBBF24` | winners, podium, badges. Used sparingly. |
| `correct` / `wrong` | `#34D399` / `#F43F5E` | the two verdicts, and nothing else |
| `rival` | `#FB923C` | the opponent's side of every scoreboard |
| `court-black` / `panel` / `raised` | `#09090B` / `#131318` / `#1C1C23` | layered surfaces |

Names are semantic, not literal, which is what lets the values change without
touching a component. `correct`/`wrong` are deliberately *not* a generic
success/error pair: nothing may borrow them to mean "saved" or "offline", or a
green flash on a question board stops meaning one thing.

**A verdict is never colour alone.** Correct settles; wrong *shakes*. Roughly 1
in 12 men cannot separate this green from this red, and "did I get it right" is
not something to leave to a hue — so there is a glyph and a motion as well.

### Responsive

The `phone` / `desk` / `short` variants switch on **viewport shape**, not width:
a phone in landscape reports ~800×360 CSS px, sails past `md`, and would
otherwise get the laptop layout. `phone` and `desk` are exact complements — any
gap between them shows both navs or neither.

`--page-fit` is the viewport minus the shell's chrome. Only one screen uses it —
the live match — because that is the one page that must not scroll: an answer
tile below the fold is an answer the clock runs out on.

---

## 10. What is not built yet

Honestly listed rather than implied by absence:

- **Google sign-in button.** The API calls and the config gate are in
  (`features/auth/api.ts`, `useAuthConfig`); the GIS script loader and the button
  are not.
- **PWA.** No manifest, no service worker. The meta tags for an iOS home-screen
  launch are in `index.html`; the rest is a `vite-plugin-pwa` block away.
- **A standalone achievements page.** Badges render on the profile, which is the
  only place the API exposes them (there is no achievements endpoint yet).
- **Rating deltas after a match.** `match.completed` doesn't carry one and the
  ladder moves inside the same transaction that ends the match, so the summary
  screen deliberately shows no `+12` it would have to guess at.
