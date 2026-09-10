# Leftovers

Small, named gaps in work that is otherwise done. Each entry says what is
missing, what it blocks, and what closing it takes — so nothing here has to be
rediscovered by tripping over it. `plan.md` is the route; this is the list of
things the route stepped over on purpose.

---

## Phase B — identity (steps 4–7, otherwise complete)

### Google sign-in has no credentials

`GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` are unset, so the
provider is deliberately left **unregistered** rather than registered with
empty strings: `GET /api/v1/auth/config/` reports `google_enabled: false`, and
`POST /api/v1/auth/google/` answers a 400 (`google_oauth_not_configured`)
instead of failing somewhere inside allauth.

Everything around it is written and tested against a *simulated* configured
tier (`apps/accounts/tests/test_google.py` — the adapter's linking rule, its
refusals, and the unconfigured behaviour). **What has never run is a real token
exchange with Google.**

To close it: register an OAuth 2.0 Web application in a Google Cloud project,
put the pair in `.env`, and sign in once. Two things can only be found that
way — the redirect/origin allow-list on the Google side, and whether the
`access_token` the client sends is the shape `dj_rest_auth`'s
`SocialLoginView` expects.

### No SMTP relay

Password reset is complete and tested, but `EMAIL_HOST` is unset. Local dev
prints the message to the console, the suite collects it in `mail.outbox`, and
production would fail at send time — loudly, which is the intent (a backend
that pretends to deliver is worse). `FRONTEND_URL` also still points at
`http://localhost:5173`, and the reset link is built from it.

To close it: a relay's SMTP credentials plus the real client origin, both as
environment variables. No code changes.

### The reset link points at a page nobody has built

`/reset-password?uid=…&token=…` is a route on the *client*. Until that exists,
`POST /auth/password/reset/confirm/` is reachable only by hand.

### The lockout numbers are guesses

`LOGIN_DELAY_AFTER=3`, `LOGIN_LOCKOUT_AFTER=10`, 15-minute window and lock —
inherited from rpool, not measured here. They are enforced by default and off
in the test settings. Worth revisiting once there are real sign-ins to count;
the counting path runs even with enforcement off, which is what makes that
possible.

### Avatars are written to the local disk

`MEDIA_ROOT` defaults to `backend/media/`, which is right for local development
and wrong for a container whose code directory is read-only. Same gap question
images already have — **step 23** owns both, and the fix is one for the two.

There is also no image *processing*: an upload is accepted at its original
dimensions (2 MB / JPEG-PNG-WEBP, decoded and verified rather than trusted by
extension). A thumbnail pipeline is worth having before this is a real load,
and no old file is cleaned up when a picture is replaced.

### `GET /players/{name}/` is not here yet

Public profiles are **step 19**, and depend on rankings and achievements
existing to have anything to show. Today `apps/players` serves only the
caller's own row plus the name-availability check.

### Account deletion

There is no "delete my account" path. `Player.user` is `SET_NULL` so the
competitor and its match history survive one, but the identity-stripping half
(what rpool calls retiring) is unwritten. It only becomes urgent when there are
matches to preserve — Phase C.
