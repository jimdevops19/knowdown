# Backend — what's left

`initial-plan.md` is the destination. This is the route: the backend work
between what exists today and a game two people can actually play.

**What exists** (see `backend/CLAUDE.md`): the Django project and its shared
contracts, the question catalog with `sync_questions`, `categories`, the
`accounts.User` model, and layered scaffolds for `players`, `matches`,
`rankings`, `achievements`.

**Sequencing.** Phase C is the product; A and B are what it needs to exist.
Phase C is deliberately built and tested **without WebSockets** — every rule of
the game is a service function callable from a test, and Phase D adds a
transport over the top. A match engine written inside a consumer is one that can
only be tested by opening sockets, which is how game logic ends up untestable.

---

## Phase A — finish the questions domain (3 steps)

### 1. Answer payloads and evaluation
Add `apps/questions/schemas/answers.py` (a pydantic union per question type, the
same discriminated shape the resource schemas use) and
`apps/questions/services/evaluation.py`: one evaluator per type behind a single
`evaluate_answer(*, question, submitted) -> AnswerResult(is_correct, score)`,
dispatched through `QUESTION_MODELS`' sibling registry.

The rules each evaluator owns: single/image — one option id; multiple — the set
must match exactly (decide partial credit here, once); true/false — a bool;
free-text — casefolded, whitespace-stripped comparison against
`accepted_answers`; ordering — the full sequence; matrix — per-cell, so a grid
can be partly right.

**The rule that matters:** evaluation belongs to the questions domain, not to
`matches`. The match engine must never learn what a correct answer looks like.

**Done when:** a table-driven test covers every type with a right, a wrong and a
malformed payload, and a malformed one raises `ValidationFailed` rather than
scoring zero — a client sending nonsense is a bug, not a wrong answer.

### 2. Play-time serializers that cannot leak an answer
`apps/questions/api/serializers.py`: one serializer per type emitting what a
player needs to *see* — the description, the options with their ids, the image
urls, the matrix headings — and nothing else. Options are shuffled per matchup,
not per player, so both sides see the same board.

**The rule that matters:** this is the whole anti-cheat surface. `is_correct`,
`answer`, `correct_position` and `MatrixCell.answer` must never appear in a
payload, and "we remembered not to include it" is not a mechanism.

**Done when:** a test walks every serializer in `apps.questions` and fails on any
field whose name is in a forbidden set (rpool's `EmailExposureTests` is the
pattern), plus a test asserting the shuffle is stable within a matchup.

### 3. Catalog depth, and a command that reports it

*(Level bands settled: three — 1-3 easy, 4-7 medium, 8-10 hard, in
`apps/questions/constants.py`. Stocking floor `CATALOG_DEPTH_TARGET = 50` per
band. The report and the refusal are in; **authoring the ~130 remaining NBA
questions is the outstanding half of this step**, to be done in reviewable
batches — `questions_report` names the shortfall.)*
`select_questions` refuses when the pool is smaller than the count asked for, so
a thin category is a broken match, not a shorter one. Add
`manage.py questions_report` — counts per category, per type, per level band —
and write NBA questions up to a floor worth naming (say 50 per level band the
matchmaker will draw from).

**Done when:** the command prints the catalog as a table and exits non-zero when
any active category cannot fill a 7-question match at every level band.

---

## Phase B — identity (4 steps)

### 4. Registration, sign-in and tokens
`apps/accounts/services/registration.py` + `api/`: `register_user` (validate
everything before writing anything, so a refusal never leaves a `User` without
its `Player`), a `LoginSerializer` that takes one `email` field and resolves it
case-insensitively itself, and mounted SimpleJWT refresh/verify. Plus
`GET /auth/config/` so a client can tell which sign-in methods a tier offers, and
`GET/PATCH /auth/me/`.

**The rule that matters:** a wrong password, an unknown address and a malformed
one are refused identically, and an unknown address is hashed against anyway so
it cannot be told apart by how fast it is refused. Sign-in must not be an
account-existence oracle.

**Done when:** `/auth/me/` is the *only* endpoint in the whole API that can emit
an email address, guarded by a test that walks every serializer.

### 5. Guessing gets slower, then stops
`apps/accounts/services/lockout.py` + a `login` throttle scope: free failures,
then a doubling cooldown, then a temporary lock, counted per **address typed**
(never per account found — asking whether it exists rebuilds the oracle step 4
removed) and hashed into the cache key.

**The rule that matters:** the delay is a 429 with `Retry-After`, never a
`sleep` — holding the request open is a free way to pin every worker. And the
lock is temporary, or it becomes a way to keep a rival out of their own account.

**Done when:** enforcement is off in the test settings and the lockout tests ask
for it back with `@override_settings`, the way the throttle tests do.

### 6. Password reset, and Google sign-in
Hand-rolled `password/reset/` + `confirm/` on their own throttle scope (the
request half sends mail on every hit regardless of whether the address exists),
`FRONTEND_URL`-built links, and allauth/dj-rest-auth with a social adapter that
matches an existing account on `email__iexact`. The refresh token rides an
HttpOnly cookie scoped to the two routes that read it; the access token is
short-lived and memory-only on the client.

**Done when:** a tier with no Google credentials leaves the provider
*unconfigured* rather than registered with empty strings, and says so through
`/auth/config/`.

### 7. `apps/players` — the competitor
`Player` per `initial-plan.md` (one-to-one back to `User`, nullable), plus
`ensure_player_for_user`, `set_display_name` as the only writer (the serializer
field is read-only so no payload can route around the validator), avatar upload,
`GET/PATCH /players/me/` and `GET /players/display-name-available/`.

**The rule that matters:** the display name is printed on every scoreboard, so it
is never a login and is never seeded from an email address — publishing it would
publish half of somebody's credential.

**Done when:** uniqueness is case-insensitive and enforced by a DB constraint as
well as a validator, so a rename to your own capitalisation is legal and a race
between two claims is a `Conflict`, not a 500.

---

## Phase C — the match engine, without sockets (5 steps)

### 8. `apps/matches` — constants and models
`constants.py` (`MATCH_QUESTION_COUNTS = (3, 5, 7)`, `QUESTION_TIME_LIMIT_SECONDS`,
`DEFAULT_PLAYER_RATING`) and the four models from the plan: `Matchup`,
`MatchupPlayer`, `MatchupQuestion`, `PlayerAnswer`.

**The rule that matters:** `MatchupQuestion` stores `(question_type, question_id)`
— the `QuestionRef` pair the selectors already return — not a foreign key. That
is what keeps the match tables independent of seven question tables, and it is
why a question is deactivated rather than deleted.

**Done when:** a constraint enforces exactly two players per matchup, and one
answer per player per question.

### 9. Match services — the whole game, callable from a test
`services/`: `create_matchup`, `select_match_questions`, `start_matchup`,
`start_question`, `submit_answer`, `complete_question`, `complete_matchup`,
`return_player_to_matchmaking`. Keyword-only, `@transaction.atomic`, no knowledge
of WebSockets.

The server picks the question count (`random.choice(MATCH_QUESTION_COUNTS)`) and
the questions, once, for both players.

**Done when:** a test plays a full 5-question match to a winner through service
calls alone, with no consumer and no socket in sight.

### 10. Server-authoritative timing and scoring
`start_question` stamps `T0`; `submit_answer` measures `T1 - T0` on the server.
Scoring combines correctness with speed — decide the curve once, in
`constants.py`, beside the numbers it uses.

**The rule that matters:** the client displays a timer; the server decides what
happened. A client-submitted `response_time_ms` is not read, ever — accepting it
makes every match winnable with a patched client.

**Done when:** a test submits an answer with a lying timestamp in the payload and
the recorded time is the server's.

### 11. The unhappy paths
A question nobody answers before the limit; a player who answers after their
opponent has already taken it; a double submission; a player who leaves
mid-match. Decide and encode: does an abandoned match award the win, void the
result, or count as a loss?

**The rule that matters:** `submit_answer` is idempotent per
`(matchup_question, player)`. A flaky connection retrying must not score twice,
and it must not be treated as cheating either.

**Done when:** every one of those four has a test, and an abandoned matchup
reaches a terminal state with no scheduled work left pointing at it.

### 12. Match history over REST
`GET /api/v1/matches/` (the caller's own) and `GET /api/v1/matches/{id}/` — the
questions played, both players' answers, the times, the result. Read-only:
scoring happens over the socket, and a REST write path would be a second
implementation of the rules.

**Done when:** a finished matchup renders with the *concrete* question of each
type, resolved through `selectors.get_question`, including questions since
deactivated.

---

## Phase D — realtime (4 steps)

### 13. Channels plumbing
Wire the `websocket` branch in `config/asgi.py` (behind
`AllowedHostsOriginValidator`), add `apps/matches/routing.py`, `consumers.py`,
`groups.py`, `publish.py`. Consumers stay thin: receive → validate → call a
service → broadcast.

**The rule that matters:** `publish` never raises. The action that triggered it
has already committed, so a Redis outage must degrade the live view, not 500 a
request that succeeded.

**Done when:** `SERVER_MODE=realtime` runs uvicorn on `config.asgi` and
`SERVER_MODE=api` runs gunicorn on `config.wsgi` from one image, and
`shared.logging.service` labels each process correctly without being told twice.

### 14. The global matchmaking pool
One logical queue in Redis — not a database row per waiting player. Pairing must
be **atomic**: two workers popping simultaneously must not hand the same
opponent to two different matches (a Lua script, or a single `BLMOVE`-style
primitive; decide and write down which).

**The rule that matters:** the pool is a transient mechanism, not a persistent
room. Nothing in PostgreSQL knows who is queued.

**Done when:** a test drives N concurrent joins and asserts every player lands in
exactly one matchup, with at most one left waiting.

### 15. Presence and reconnection
`ONLINE / SEARCHING / MATCHED / PLAYING / OFFLINE` in Redis, with TTLs so a
process that dies does not strand a player as permanently online. A reconnect
inside a live matchup rejoins the group and receives the current question and the
server's remaining time.

**Done when:** killing and restarting the realtime process leaves no player stuck
in `SEARCHING`, and a mid-match refresh resumes rather than forfeits.

### 16. The event protocol, end to end
`MATCH_FOUND`, `QUESTION_STARTED`, `PLAYER_ANSWERED`, `QUESTION_RESULT`,
`MATCH_COMPLETED` — defined in one module, versioned with the API, and documented
where a client author will find it.

**Done when:** two `WebsocketCommunicator`s play a full match against the real
consumer, and a test asserts that no frame sent before `QUESTION_RESULT` contains
anything that identifies the correct answer.

---

## Phase E — progression (3 steps)

### 17. `apps/rankings` — a rating per category
`Ranking` per the plan (player × category), an Elo-style update in
`services/ratings.py` with the K-factor in `constants.py`, and a seeding hook so
a player entering a category starts at `DEFAULT_PLAYER_RATING`. Plus a
`backfill_rankings` command for players who predate a category.

**The rule that matters:** ratings are per category. There is no global number,
because being good at NBA trivia says nothing about F1.

**Done when:** `complete_matchup` updates both sides in one transaction, and a
ladder read is one query rather than one per player.

**Important: the rating calculation should follow the same mechanism like in the repo of rpool - ratings start for 1200 each and each matchup after completion of the best of X rises or falls the rating, depending on the rating numberp played, inspect ~/repos/rpool/backend/apps/rankings/ to capture the logic - pay attention that rpool has competitive logic for rankings addition substraction, here in knodown it's not relevant, ratings are counted in each matchup**

**Step 17 done (10/09/2026):** `Ranking` (player × category, `DEFAULT_PLAYER_RATING`
still living in `apps.matches.constants`), `apps/rankings/services/ratings.py`
(`expected_score` / `update_rating`, `K_FACTOR` in `apps/rankings/constants.py`,
no rpool-style guest/race-length/audit-trail machinery — every completed
matchup counts once, a tie is a 0.5/0.5 draw), `ensure_ranking` as the seeding
hook, `manage.py backfill_rankings`, and `selectors.ladder` as the one-query
read. Wired into `apps.matches.services.complete_matchup` and
`abandon_matchup`, both now updating both sides' ratings once terminal. 266/266
backend tests pass (`apps.rankings` adds 49 of them).

### 18. `apps/achievements`
`Achievement` + `PlayerAchievement` with the unique constraint from the plan, the
initial eight badges as a **resource file loaded by a command** — the same
authoring loop as questions, for the same reason — and evaluation hooked to match
completion.

**The rule that matters:** an achievement is checked from the match result, not
sprinkled through the match services. One place decides, so a new badge is a rule
in one module and not a line added to five.

**Done when:** re-running the loader is idempotent, and awarding is idempotent —
a replayed completion cannot grant "First Win" twice.

**Step 18 done (10/09/2026):** `Achievement` (`SluggedModel` + `BaseModel`, like
`Category`) + `PlayerAchievement` (plain `models.Model`, like `PlayerAnswer` —
no independent existence). The eight badges in
`apps/achievements/resources/achievements.yaml`, loaded by
`manage.py sync_achievements` (upsert on slug, deactivate-not-delete, same
shape as `sync_questions` at a tenth of the size). `services/evaluation.py`'s
`ACHIEVEMENT_RULES` registry (slug → rule function) is the one place a badge
is checked; `award_achievements_for_matchup` is the hook, called from
`apps.matches.services.complete_matchup`/`abandon_matchup` **before**
`apps.rankings.services.update_ratings_for_matchup` so "Beat a Higher Rated
Player" reads each side's pre-match `Ranking`. Awarding idempotent via
`PlayerAchievement`'s unique constraint + `get_or_create`.

### 19. Profile and leaderboards
`GET /players/{name}/` (public profile: rating per category, record, badges) and
`GET /rankings/{category}/` (the ladder, paginated). Both read-only, both through
selectors that already filter to what a caller may see.

**Done when:** a profile is one round trip and the ladder is paginated by default.

**Step 19 done (10/09/2026):** `GET /api/v1/players/{display_name}/`
(`AllowAny`, case-insensitive lookup, one query per embedded list via
`rankings.selectors.list_rankings_for_player` /
`achievements.selectors.list_earned_for_player`) and
`GET /api/v1/rankings/{category}/` (`AllowAny`,
`apps.core_common.pagination.DefaultPagination`, best rating first). Phase E
is now complete: 297/297 backend tests pass, `manage.py spectacular
--fail-on-warn` is clean.

# STOPPED HERE - 10/09/2026 - Phase E complete (18, 19 done); Phase F not started

---

## Phase F — hardening and shipping (6 steps)

### 20. Abuse limits on the paths that cost something
A throttle scope for answer submission and for entering matchmaking; a cap on
concurrent sockets per account. Counting before enforcing, so the numbers are
real on the day the limit is switched on.

**Done when:** enforcement is off in the test settings and the limit tests ask for
it back explicitly.

### 21. `apps/ops` — the admin's door
Port rpool's admin gate: the mounted prefix 404s from outside and the admin
answers only under a token minted by `manage.py open_admin --minutes 30`, stored
hashed, closed by `close_admin` or its own clock.

**The rule that matters:** a row rather than an environment variable, because
opening the admin must not roll a deployment, must be visible to every worker,
and should leave a record of who opened it.

**Done when:** the live token never appears in an access-log line (path redaction
has a test).

### 22. Container and deploy
`backend/Dockerfile` + `entrypoint.sh` branching on `SERVER_MODE`,
`manage.py migrate_locked` (migrate under an advisory lock, so replicas starting
together serialise instead of racing), `collectstatic` at build time, health
probes wired to the two endpoints that already exist.

**Done when:** `replicas > 1` is safe, and the API and realtime processes can
never come from different commits.

### 23. Question images off the local disk
`MEDIA_ROOT` on a writable volume, or object storage. Today `sync_questions`
copies into the code directory, which is correct for local dev and wrong for a
container whose code dir is read-only.

**Done when:** a fresh deploy serves an image-answer question with no manual copy
step.

### 24. CI
Run the suite on every push, `pip-audit` on the dependency group, and generate
the OpenAPI document offline (`manage.py spectacular`) so a client's types can be
built without a running server.

**Done when:** a red suite blocks a merge, and the schema artefact is attached to
the build.

### 25. Journey logging and a load rehearsal
Log the route through the product, not just its endpoints — `Player queued`,
`Match found`, `Question answered`, `Match completed` — on the existing field
schema. Then rehearse: N simulated players against a deployed instance,
answering at human speed, with a teardown command that purges only the rows the
run tagged.

**Done when:** "how many matches completed, and how long did players wait for an
opponent?" is a log query rather than a guess.

---

## Decisions still open

These change the code and are cheaper to settle before the phase that needs them
than after:

- **Scoring.** Is speed a multiplier on a correct answer, or a separate points
  pool? Does a wrong answer cost anything? (Step 10)
- ~~**Partial credit** on multiple-answer and matrix questions~~ — **settled
  (step 1)**: all-or-nothing for single, image, true/false, free-text and
  ordering; **exact set** for multiple-answer; **per authored cell** for matrix.
  `AnswerResult` carries `is_correct` *and* `score` (credit 0.0–1.0) so the two
  can disagree, which they do only for a matrix. Step 10 combines that credit
  with speed; it does not re-decide it.
- ~~**Abandonment.**~~ — **settled (step 11)**: the remaining player is awarded
  the win (`services.abandon_matchup`), never a void — voiding would erase
  whatever they had already earned. The matchup reaches `COMPLETED` with
  `outcome=abandoned`, which is what lets `apps.rankings` (step 17) touch both
  sides' ratings exactly the way any other result does, once.
- ~~**Scoring.**~~ — **settled (step 10)**, in `apps.matches.constants.score_answer`:
  one curve, not a separate pool. A wrong (or partially wrong) answer earns
  nothing regardless of speed; a correct one is worth
  `MAX_QUESTION_POINTS × credit × speed_factor`, floored at `MIN_SPEED_FACTOR`
  so a hard question worked out right at the wire is not scored like a guess.
- **Whether a match is single-category.** `Matchup.category` says yes; that means
  matchmaking is per category, and the "one global pool" is really one pool per
  active category the moment there are two. (Step 14)
- **Rematch.** Both players return to the global pool — is there a "play again
  with the same opponent" path, and does it skip the queue?
  `services.return_player_to_matchmaking` exists today only as the validated
  seam Phase D's pool will call; it decides nothing about rematch itself. (Step 14)
- **Question repetition.** Should a player be able to draw a question they have
  already seen this week? Answering "no" needs a per-player seen-set, which is a
  Redis structure and a decision about how long it lives. (Step 14, once a pool exists)
