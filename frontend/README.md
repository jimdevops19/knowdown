# knowdown — frontend

The React SPA for **knowdown**, the real-time 1v1 trivia game. Vite + React 19 +
TypeScript + Tailwind v4, talking to the Django API at `/api/v1/` and to the
Channels realtime service at `/ws/v1/`.

`ARCHITECTURE.md` is the blueprint — read it before writing any fetch.

## Running it

The backend has to be up first (see the repo root's `README.md`); this app
proxies to it rather than talking cross-origin.

```bash
# from the repo root, in one terminal
cd backend
uv run python manage.py runserver

# in another
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Zero-config: with no `.env` the dev server proxies `/api`, `/ws` and `/media` to
`http://127.0.0.1:8000`, which is where `runserver` puts them. Copy
`.env.example` to `.env.local` only if your backend is somewhere else.

> **The realtime half needs an ASGI server.** `manage.py runserver` serves both
> HTTP and WebSockets under Channels, so plain `runserver` is enough for
> development. In a deployment they are two processes — gunicorn for the API,
> uvicorn for `config.asgi` — with nginx splitting `/api/` from `/ws/`.

```bash
npm run build          # tsc -b && vite build
npm run test           # vitest, jsdom
npm run lint           # oxlint
```

## Where things are

```
src/
  app/           router, providers, AppShell + the phone tab bar
  lib/
    api/         axios client, the error model, the domain types, REST wrappers
    realtime/    the WebSocket layer — the match state machine lives here
    query/       the React Query client and every query key
  features/
    auth/        session, the token store, the route guard
    play/        the game: the boards, the clock, the scoreboard, the summary
    players/     the display-name field and its live availability check
  components/    the design system's primitives
  pages/         one file per route
```

## Two things to know before changing anything

**REST is the past; the socket is the game.** Finding an opponent, seeing a
question, answering it and learning the result all happen over the WebSocket,
because the thing being raced is the server's clock and a round trip is not a
clock. REST answers history, profiles, ladders and the catalog — never a move.
`lib/api/endpoints.ts` has no function that plays anything, and that is
deliberate.

**Nothing that crosses the wire while a clock is running may name an answer.**
The backend enforces this by refusing to boot if a play-time serializer declares
a forbidden field. This side keeps its half honestly — boards render only the
fields they name, and `features/play/QuestionBoard.test.tsx` feeds every board a
deliberately poisoned payload to prove none of it reaches the DOM.

## Design system

Dark only. Violet primary, cyan accent, near-black layered surfaces — the whole
theme is tokens in `src/index.css`, so a restyle is one file. The token *names*
are semantic (`court`, `volt`, `correct`, `wrong`, `rival`), not literal, which
is what lets the values change without touching a component.

Phone-first, and meant literally: a phone in landscape is still a phone, so the
`phone` / `desk` / `short` variants switch chrome on "is this viewport
phone-shaped" (narrow **or** short) rather than on width alone. The live match
screen is the one page in the app that must not scroll — see `--page-fit`.
