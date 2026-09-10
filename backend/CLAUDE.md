# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Knowdown** — a real-time 1v1 trivia backend. Two players enter one global
matchmaking pool, get paired, and race through 3/5/7 questions; the fastest
correct answer wins the question, the winner takes rating and achievements, and
both go back into the pool. The first category is NBA, and **categories are
independent of question types** on purpose, so the same engine can eventually
run Premier League, F1 or UFC.

Django 6 + Django REST Framework, JSON API under `/api/v1/`, Python 3.13,
dependencies managed with **uv**. The repo root holds `pyproject.toml`,
`uv.lock` and `.venv`; the Django project lives in `backend/`. Run `uv` commands
from either; run `manage.py` from `backend/`.

`initial-plan.md` at the repo root is the product/architecture plan this is being
built toward. It is the intent, not the state — read this file for what exists.

### What exists today

The question authoring pipeline and the scaffolding under it:

- **`apps/questions`** — every question shape, the pydantic schemas that validate
  the authored YAML, `sync_questions`, the selection seam the match engine will
  call, **answer evaluation** (`services/evaluation.py`) and the **play-time
  serializers** that must never leak an answer (`api/serializers.py`).
  `questions_report` says whether the catalog is deep enough to play.
- **`apps/categories`** — the `Category` model and a read-only endpoint pair.
- **`apps/accounts`** — **identity**: registration, email/password sign-in,
  JWT lifecycle, the sign-in lockout, password reset, Google sign-in, and
  `/auth/me/` — the one endpoint in the API that may emit an email address.
- **`apps/players`** — the **competitor**: a display name (unique
  case-insensitively, in the database as well as in a validator), an avatar,
  `GET/PATCH /players/me/`, and the public profile,
  `GET /players/{display_name}/` (rating per category, record, badges — one
  round trip, `AllowAny`).
- **`apps/core_common`**, **`shared/`** — the platform-wide contracts (below).
- **`apps/matches`** — the **match engine**: `Matchup`, `MatchupPlayer`,
  `MatchupQuestion`, `PlayerAnswer`, and every rule of a game as a `services`
  function callable from a test (`create_matchup` through `abandon_matchup`) —
  `services/` still imports nothing from `channels`. Read-only match history
  over REST for **finished** matches only (`GET /api/v1/matches/`,
  `GET /api/v1/matches/{id}/` — see "matches" below for why live ones are
  refused), and the
  **realtime transport** over the top: a global matchmaking pool
  (`apps.matches.pool`), presence (`apps.matches.presence`), and two
  WebSocket consumers (`consumers.py`) that turn the same service calls into
  `events.py`'s live protocol. See "Realtime" below.
- **`apps/rankings`** — a rating per player, **per category** (`Ranking`).
  Elo-style (`services/ratings.py`, `K_FACTOR` in `constants.py`), moved once
  per matchup: `apps.matches.services.complete_matchup` and `abandon_matchup`
  both call `update_ratings_for_matchup` after deciding the winner, so a
  played-out match and an abandoned one move the ladder the same way. A tie
  counts as an Elo draw (0.5 each) rather than being skipped. No audit trail —
  unlike a tournament ladder, nothing here is ever replayed or unwound.
  `manage.py backfill_rankings` seeds a category's missing players (one who
  predates it, or predates the seeding hook itself) at `DEFAULT_PLAYER_RATING`
  — which lives in `apps.matches.constants`, not here, because seeding happens
  the moment a matchup needs a rating that is not there yet. Read-only,
  paginated leaderboard: `GET /rankings/{category}/`.
- **`apps/achievements`** — the badge catalog (`Achievement`,
  `PlayerAchievement`), authored the same way a question is:
  `resources/achievements.yaml` + `manage.py sync_achievements`, upserted on
  `slug`, deactivated rather than deleted. `services/evaluation
  .ACHIEVEMENT_RULES` is the one registry a badge's rule lives in; every rule
  is checked from `award_achievements_for_matchup`, the hook
  `apps.matches.services.complete_matchup`/`abandon_matchup` call **before**
  `apps.rankings.services.update_ratings_for_matchup` — "Beat a Higher Rated
  Player" needs each side's pre-match rating, which the ratings call is what
  moves. Awarding is idempotent (`PlayerAchievement`'s unique constraint backs
  a `get_or_create`), so a matchup that cannot complete twice cannot grant a
  badge twice either. Embedded in the player profile
  (`GET /players/{display_name}/`); no standalone list endpoint yet.

## Commands

```bash
# Install / sync deps (from the repo root)
uv sync

# All manage.py commands run from backend/ and default to config.settings.local
uv run python manage.py runserver
uv run python manage.py migrate
uv run python manage.py makemigrations
uv run python manage.py createsuperuser   # asks for an email, not a username

# Tests — always with the test settings (in-memory sqlite, fast hashing, quiet logs)
uv run python manage.py test --settings=config.settings.test
uv run python manage.py test apps.questions --settings=config.settings.test
uv run python manage.py test apps.questions.tests.test_evaluation --settings=config.settings.test
uv run python manage.py test apps.accounts apps.players --settings=config.settings.test
uv run python manage.py test apps.matches --settings=config.settings.test
```

`apps/questions/tests/` is a **package**, not a `tests.py` — the loader's
refusals, the evaluator's verdicts, the serializers' silence and the report's
exit code are unrelated subjects, and the third of them is the anti-cheat
surface, which is worth being findable. `tests/factories.py` builds question rows
straight through the ORM; only `test_sync` goes the long way round through a
resources tree, because the loader is what it is testing.

### `sync_questions` — the one custom command

```bash
uv run python manage.py sync_questions              # load everything
uv run python manage.py sync_questions --dry-run    # validate + report, write nothing
uv run python manage.py sync_questions --category nba
uv run python manage.py sync_questions --categories-only
```

Loads `apps/questions/resources/` — `categories.yaml` plus a folder of YAML per
category — into the database. **Idempotent, upserting on `slug`**: editing a
question's wording and re-running corrects the row rather than inserting a second
copy of it, which is what makes the resource files the source of truth rather
than a one-time seed. Four rules hold it together:

- **Nothing is deleted.** A question dropped from the YAML is *deactivated*,
  because a matchup that already played it points at that row — a hard delete
  would edit a game two people have already finished. Same for a category.
- **Everything is validated before anything is written.** Every file is parsed
  and cross-checked up front, and problems are collected across all of them, so a
  typo in the last file neither leaves the first half loaded nor hides the other
  four mistakes.
- **The sweep is scoped to what was loaded.** `--category nba` deactivates only
  missing NBA questions; it cannot quietly retire another sport.
- **Images are copied by content digest.** A re-sync of an unchanged catalog
  moves no bytes, so running this on every deploy is cheap.

The command cannot be spelled `sync-questions` — Django finds a command by
importing the module named after it, and a hyphen is not a legal module name.

### `questions_report` — is the catalog deep enough to play?

```bash
uv run python manage.py questions_report
uv run python manage.py questions_report --category nba
uv run python manage.py questions_report --count 3        # could we run 3-question matches?
uv run python manage.py questions_report --include-inactive
```

Prints the catalog as two tables — depth per level band, depth per question type
— and **exits non-zero when an active category cannot fill a
`LONGEST_MATCH_QUESTION_COUNT`-question match at every level band**. That is the
point of it: a thin band is a band where matchmaking *refuses*
(`selectors.select_questions`), so a deploy pipeline should find out before two
players do. The stocking target (`CATALOG_DEPTH_TARGET`, the depth at which a
band stops being the same board every time) prints as a shortfall and does
**not** fail the command — refusing there would take a category out of service
for being merely repetitive.

Config is 12-factor via environment / a repo-root `.env` (see `.env.example`);
`DJANGO_SETTINGS_MODULE` selects the module (`config.settings.{local,test,production}`,
default `local`). With no `.env` it falls back to local sqlite, an in-memory
channel layer and an in-memory cache, so it runs zero-config.

API docs at `/api/docs/` (schema at `/api/schema/`) — **mounted only when
`DEBUG`**. Probes: `/api/v1/health/live/` (process only, for `livenessProbe`) and
`/api/v1/health/` = `/api/v1/health/ready/` (checks the DB, for `readinessProbe`).

**The Django admin is off by default and is not at `/admin/`.** `ADMIN_ENABLED`
mounts it; `ADMIN_URL` sets the prefix, and with none configured a random
40-character one is generated per process. `runserver` prints the URL it picked
(`local.py` enables the admin), which is the only place it is ever announced.

## Architecture

This follows the **HackSoft Django Styleguide**: business logic lives in
services/selectors, not in views or models. Every app under `apps/` has the same
layered layout:

- **`api/`** — `views.py`, `serializers.py`, `urls.py`. Views are **thin**: parse
  input → call one selector or service → serialize output. Each app owns its
  `api/urls.py`, included by `config/urls.py`.
- **`selectors/`** — the **read** side. Query functions returning
  querysets/objects. Never mutate. Raise `NotFound` when a lookup fails.
- **`services/`** — the **write** side. Mutations and orchestration, wrapped in
  `@transaction.atomic`.
- **`validators/`** — pure domain-rule predicates that raise on violation.
  Distinct from serializer validation, which only checks request *shape*.
- **`schemas/`** — pydantic models for data that arrives as a *file* rather than
  as a request (today: the question resources).
- **`models.py`**, **`permissions/`**, **`admin.py`**, **`tests.py`**.

### questions — one table per answer shape, held together by a registry

A **category** says what a question is about; a **question type** says how it is
answered. Neither knows about the other, and that is the whole design: adding UFC
is a row in `categories.yaml` and a folder of YAML, adding a new way to answer is
a model — and never both.

Each answer shape is its own concrete table (`SingleAnswerQuestion`,
`TrueFalseQuestion`, `ColumnsRowsQuestion`, …) rather than one table with
nullable columns or multi-table inheritance: the *options* differ in kind — a
text option, an image option, a cell in a grid — and a shared parent would buy
one primary key at the price of a join on every read.

**`models.QUESTION_MODELS` is what holds them together.** The loader reads it to
map a YAML `type:` to a model, the selectors read it to draw from every shape at
once, the admin reads it to register them.

It now has three siblings, all keyed by the same `QuestionType` value, one per
thing you can do with a question:

| registry | module | says |
| --- | --- | --- |
| `QUESTION_MODELS` | `models` | the type exists, and which table it is |
| `ANSWER_SUBMISSIONS` | `schemas.answers` | what answering it looks like on the wire |
| `ANSWER_EVALUATORS` | `services.evaluation` | what counts as right |
| `QUESTION_SERIALIZERS` | `api.serializers` | what a player may see of it |

Adding a question type is: a model, a `QuestionType` member, a resource schema
variant, and **one line in each of the four** — plus a builder in
`tests/factories.py`, which is what puts it into every table-driven suite for
free. `tests.test_evaluation.RegistryCoverageTests` walks all of them together,
so a type that can be *asked* and not *scored* fails the suite rather than a
live match stuck on question three.

Three consequences worth keeping:

- **A question carries a `slug`, which `initial-plan.md` does not mention.** It is
  the upsert key — without a stable key of its own, correcting a typo in a
  question would insert a second copy beside it. It is unique per table by
  constraint and unique across *every* question table by the loader, because
  `MatchupQuestion` will identify a question by `(question_type, question_id)`
  and a slug meaning two things is a question nobody can name in a bug report.
- **`selectors.QuestionRef`** — a `(question_type, question_id)` pair — is what
  stands in for "a question" wherever the type is not known ahead of time. It is
  why the match tables will need no foreign key into seven question tables.
- **Selection and evaluation live in `questions`, not in `matches`.** The match
  engine must stay independent of the concrete question type, so "give me five
  NBA questions" (`selectors.select_questions`) and "is this answer correct?"
  (`services.evaluate_answer`) are questions this domain answers and the match
  domain merely asks. The match engine must never learn what a correct answer
  looks like; it decides what a verdict is *worth*, not what is true.
- **A thin category is a broken match, not a shorter one.** `select_questions`
  refuses when the pool is smaller than the count asked for, rather than playing
  a shorter match — otherwise the length of a game would depend on how well
  stocked a category happens to be. `constants.LEVEL_BANDS` cuts the 1..10 scale
  into the three bands the matchmaker will draw from (nothing *stores* a band — a
  question stores its level), and `selectors.catalog_depth` is how
  `questions_report` asks whether each one can be played.

Positions and orders (`option.order`, `correct_position`, matrix row/column
`order`) are **derived from the list order in the YAML**, never authored — which
is why no resource file can have a gap or a duplicate position.

#### Answering: three outcomes, not two

`schemas/answers.py` is the payload contract (a discriminated union, strict about
shape, `extra="forbid"`); `services/evaluation.py` is the verdict. A submission
is right, wrong, or **not an answer at all** — and the third raises
`ValidationFailed` rather than scoring zero, because a client sending nonsense is
a bug, and "anything I do not understand is worth zero" is the behaviour a
patched client probes for. Running out of time is not that case: no payload
arrives.

`AnswerResult` carries `is_correct` **and** `score` (credit, 0.0–1.0) because
they disagree on exactly one type. Partial credit, settled once: all-or-nothing
for single, image, true/false, free-text and ordering; **exact set** for
multiple-answer (per-option credit would make the shotgun a strategy);
**per authored cell** for matrix (a grid is genuinely several sparse,
independent claims). Points are speed and stakes as well as truth, and those are
`apps.matches`' to combine — a scoring curve in `questions` would mean two places
deciding what a question is worth.

**A matrix cell accepts several answers, and any one of them takes it.**
`MatrixCell` holds no answer of its own; `MatrixCellAnswer` rows hang off it,
the sibling of `FreeTextAnswer` — because the grids worth asking ("name a player
who played for both these teams") have as many right answers per square as the
rosters share, and a single `answer` column made whichever name the author
thought of first the only one that scores. A cell is still **one** cell of
credit however many names fill it: the denominator is authored cells.

Each answer carries `probability_score`, 2–10, hand-graded: how obvious the pick
is (Michael Jordan for Bulls × Wizards is a 2; a one-season backup is a 10),
defaulting to `DEFAULT_PROBABILITY_SCORE` (5) — the middle, meaning *ungraded*.
**Nothing reads it yet**, deliberately: paying more for a rarer name would mean
two players who both filled the grid in correctly scored differently, which is a
decision about what a question is worth and so `apps.matches`'. It is authored
now because it is a judgement about the sport that only a question author can
make, and grading a catalog after the fact is the expensive order to do it in.
It never reaches a client — a square whose answers are all 9s narrows the guess.

**A grid says where its answers come from: `ColumnsRowsQuestion.kind`**
(`models.MatrixKind`). `authored` is the default and the original — every
accepted answer is a `MatrixCellAnswer` row written by hand. `teams` is the grid
whose answer key is a *fact* rather than a judgement: both axes name NBA
franchises, a cell is filled by anybody who played for both, and the file
authors **no cells at all** — the loader derives every intersection the two
rosters actually shared, and `apps.questions.rosters` answers them at scoring
time from `artifacts/nba_player_teams.csv` (baked by
`scripts/bake_nba_player_teams.py`). Writing them out instead would be tens of
thousands of rows per question, copied again by the next question that asked
about the same franchise, and stale the day somebody is traded; re-baking the
CSV now updates every one of these questions at once, and none of them needs
reloading for it.

The kind is stored rather than inferred from "does this grid have answer rows?"
— a grid with none is otherwise exactly what an authoring mistake looks like —
and everything else about a grid is unchanged: same per-cell credit over the
cells the question asks for, same refusal for a cell nobody was asked about,
same silence about answers on the wire. Three things are refused at **load**
time, where a mistyped franchise is a typo rather than a column no answer can
fill: a heading naming no franchise in the artifact, a `kind: teams` grid that
also authors `cells`, and a set of franchises that never shared a single player.
The artifact is read once per process, lazily, and only by a question that asked
for it; players are matched by **id**, never by name, because two players have
shared a name and a name-keyed index would score "played for both" for a pair of
namesakes who each played for one.

#### `api/serializers.py` is the anti-cheat surface

The question row holds the answer; the payload sent while the clock runs must
not. "We remembered not to include it" is not a mechanism, so there are three:
every serializer is a plain `Serializer` with an explicit field list (a
`ModelSerializer` grows a field when a *model* grows a column); the base class
checks its subclasses' field names **and sources** against
`FORBIDDEN_FIELD_NAMES` at class creation, so a leak fails at **import**; and
`tests/test_serializers.py` walks both the declared fields and the *rendered*
payloads of all seven types, including for the answer values themselves. The
question `slug` is omitted for the same reason — `kobe-81-point-game` is an
ordinary slug and a complete answer.

The board is **shuffled per matchup, not per player** (`shuffle_seed` is a
function of the matchup and question ids, nothing else): both sides of a race
must read the same board, two processes must agree without coordinating, and a
reconnecting player must get the board they left. Ordering questions are the case
where the shuffle *is* the anti-cheat — their options are stored in answer order.
`serialize_for_play(question=…, matchup_id=…)` is the entry point, and
`matchup_id` is required so the play path cannot produce an unshuffled board by
omission.

### accounts + players — one person, two rows

`accounts.User` is who signs in; `players.Player` is who appears on a
scoreboard. They are separate rows joined by a nullable one-to-one, and the
split is the whole security story of this half of the backend:

- **the email address is a credential**, and it leaves the API in exactly one
  place — `GET /api/v1/auth/me/`, which is `IsAuthenticated` and answers with
  `request.user`, so the only address it can emit is the caller's own.
  `apps/accounts/tests/test_email_exposure.py` walks *every* serializer in
  `apps/` and fails on any other one carrying an `email` field (rpool's
  `EmailExposureTests` is the pattern);
- **the display name is published**, so it is never a login and is never
  seeded from an address. A new player gets a generated `player_9f2c1a`
  (`has_auto_name`) and chooses a real one through `PATCH /players/me/`.
  Seeding it from an email would publish half of somebody's credential;
  accepting it at sign-in would hand out the other half.

Everything else follows from those two:

| door | route | what holds it |
| --- | --- | --- |
| sign up | `POST /auth/registration/` | `login` throttle scope |
| sign in | `POST /auth/token/` | `login` scope **+** `services.lockout` |
| refresh / verify / logout | `POST /auth/token/refresh/`, `token/verify/`, `logout/` | the refresh cookie, blacklisted on rotation |
| Google | `POST /auth/google/` | `login` scope; 400s where unconfigured |
| forgot password | `POST /auth/password/reset/{,confirm/}` | `password_reset` scope |
| who am I | `GET/PATCH /auth/me/` | `IsAuthenticated` |
| the competitor | `GET/PATCH /players/me/`, `GET /players/display-name-available/` | `IsAuthenticated` |

**Sign-in is not an account-existence oracle.** A wrong password, an unknown
address and a malformed one are refused identically — same status, same code,
same sentence — and an unknown address is hashed against anyway, because
answering it faster is itself an answer. The `email` field is a `CharField`,
not an `EmailField`, for the same reason: a 400 for a malformed address beside
a 401 for an unknown one is a difference worth nothing to a person and
everything to a script. `password/reset/` keeps the same promise from the other
side: it answers one generic 200 either way, and the branch on "does this
account exist" lives inside the service, unlogged by address.

**Guessing gets slower, then stops** (`services/lockout.py`). Free failures,
then a doubling cooldown, then a temporary lock — counted per **address typed**
(never per account found: asking whether one exists rebuilds the oracle) and
hashed into the cache key, so listing the cache does not list who has been
signing in. The delay is always a 429 with `Retry-After`, never a `sleep`:
holding the request open would be a free way to pin every worker. The lock is
temporary, or it becomes a way to keep a rival out of their own account.
Enforcement is off in the test settings; the lockout tests ask for it back with
`@override_settings(LOGIN_LOCKOUT_ENFORCED=True)`, the way the throttle tests do.

**The refresh token never reaches JavaScript.** It rides an HttpOnly cookie
(`knowdown_refresh`) scoped to `/api/v1/auth/`, is rotated on every use and
blacklisted after rotation; the access token is short-lived and memory-only on
the client. `_issue_refresh_cookie` is why the plain SimpleJWT views strip it
out of their own bodies — dj-rest-auth only does that for its own.

**Google sign-in is opt-in, and unconfigured is a state the code knows about.**
With no `GOOGLE_OAUTH_CLIENT_ID`/`_SECRET` the provider is left *unregistered*
rather than registered with empty strings, `GET /auth/config/` reports
`google_enabled: false`, and `POST /auth/google/` refuses in words instead of
failing deep inside allauth. `PERMIT_PASSWORD_AUTH` is the same idea for the
other door: off, the password routes are not mounted at all — nothing to
throttle, nothing to enumerate, nothing in the OpenAPI document.

`accounts.adapters.SocialAccountAdapter` carries the social half of two
guarantees: every account gets a `Player` (`ensure_player_for_user`, idempotent
and called from every path that can make an account), and a Google login whose
*verified* address already belongs to a local account is **linked** to it rather
than refused — allauth would otherwise redirect to a signup form this JSON API
does not route, which surfaces as a 500.

**The display name is written in one place.** `services.set_display_name` is
the only writer; the serializer field is read-only and the view calls the
service, so no payload shape reaches the column. Uniqueness is enforced twice —
a validator for the message, and a `UniqueConstraint` on `Lower("display_name")`
for the truth — which is what makes a rename to your own capitalisation legal
and a lost race a `Conflict` rather than a 500.

### matches — the whole game, without a socket in sight

`Matchup` → `MatchupQuestion` → `PlayerAnswer` is what happened; `MatchupQuestion`
stores `(question_type, question_id)` — the `QuestionRef` pair
`apps.questions.selectors` already returns — rather than a foreign key into one
of the seven question tables, for the same reason `questions` keeps evaluation
away from `matches`: this app must stay independent of every answer shape, and
that pair is what a since-deactivated question still resolves through
(`selectors.get_question`) when a finished matchup is replayed over REST.

Every rule lives in `services/`, keyword-only and `@transaction.atomic`, and is
playable start-to-finish from a test: `create_matchup` draws the question count
(`random.choice(MATCH_QUESTION_COUNTS)`) and the board once, for both players;
`start_matchup`/`start_question` stamp the server's own clock; `submit_answer`
asks `apps.questions.services.evaluate_answer` for a verdict and combines it with
a **server-measured** response time (`constants.score_answer`) — there is no
parameter anywhere in this app a client could use to report its own elapsed
time, which is what makes a patched client unable to win a question by lying
about its stopwatch. `complete_question` refuses to close a question early
unless every player has answered or the time limit has actually elapsed, so a
client cannot race the opponent's clock by asking the server to call time.

**Decided once, here, because `plan.md` left them open:**

- **Scoring** is a single curve, not a separate points pool: a wrong (or
  partially wrong) answer earns nothing regardless of speed, and a correct one
  is worth `MAX_QUESTION_POINTS × credit × speed_factor`, floored at
  `MIN_SPEED_FACTOR` so a hard question worked out right at the wire is not
  scored like a guess.
- **Abandonment** (`services.abandon_matchup`) awards the remaining player the
  win rather than voiding the match or leaving it open — voiding would erase
  whatever they had already earned, and the matchup still needs to reach
  `COMPLETED` so `apps.rankings` (step 17) can update both sides' ratings
  exactly once, the same as any other result. `Matchup.outcome` (`played` /
  `abandoned`) is how a caller tells the two apart without inferring it from
  which rows exist.
- **Idempotency** is doubled the way display-name uniqueness is in
  `apps.players`: `submit_answer` looks up an existing `PlayerAnswer` before
  scoring, and a `UniqueConstraint` on `(matchup_question, player)` is the
  backstop if two attempts still race.

`GET /api/v1/matches/` and `/{id}/` are read-only on purpose — scoring happens
through `services`, over a socket once Phase D exists, and a REST write path
would be a second implementation of the same rules. The detail serializer
reuses `questions.api.serializers.serialize_for_play` for each question's board
rather than inventing a second payload shape, so a box score inherits the
anti-cheat guarantee instead of re-deciding it.

**Both are about *finished* matches, and that is anti-cheat, not tidiness.**
`serialize_for_play` guarantees no board names its answer; it cannot guarantee
anything about *which* boards, or *whose* answers, a caller is handed. A player
in a live match is a legitimate party to it and knows its id — it is in the URL
of the screen they are on — so every ownership check on `/{id}/` passes while
the clock is running. Three gates close what that left open:

- `selectors.list_matchups_for_player` filters to `FINISHED_STATUSES`. A row
  carries both sides' `score` and `correct_answers`, and `services.submit_
  answer` increments those when an answer *lands*, not when the question
  closes — so an unfiltered list, polled through a ten-second window, reported
  whether the opponent's answer was right. `events.PLAYER_ANSWERED` refuses to
  say that on purpose.
- `MatchHistoryDetailView` answers 409 `matchup_in_progress` unless the matchup
  is finished. Not 403: the right person is asking at the wrong time.
- The detail serializer is the second mechanism behind that view, so a future
  caller reaching it another way leaks nothing either — `get_questions` emits
  only questions with a `completed_at`, and `get_answers` returns `{}` for one
  still open. Filtering unplayed questions matters past the final whistle too:
  an abandoned match's undrawn questions go back in the category pool and can
  be dealt to that player again, which made "abandon, then read the box score"
  a way to farm boards.

Each player's own submission is shown beside a played question, never the
opponent's until the question that produced it has closed.

### core_common — shared conventions (read before touching cross-cutting behavior)

- **`models.BaseModel`** — the default base for domain models: UUID primary key
  (opaque, URL-safe), `created_at`/`updated_at`, and **soft delete**
  (`deleted_at`). `.delete()` soft-deletes and *cascades* through the same
  `Collector` Django's own delete uses (`core_common.deletion`), so
  CASCADE/PROTECT/SET_NULL behave identically; `.hard_delete()` for real
  deletion, `.restore()` to undo. `Model.objects` excludes soft-deleted rows,
  `Model.all_objects` includes them — which is why the loader upserts through
  `all_objects` and clears `deleted_at`: a soft-deleted row still holds its slug
  in the unique index, so it must be revived rather than inserted beside.
  (`accounts.User` is the exception — it subclasses `AbstractBaseUser` and keeps
  no soft delete, because an account must really disappear.)
- **Response envelope** — `renderers.EnvelopeJSONRenderer` wraps every success
  body as `{"data": ...}`; paginated responses add `{"data": [...], "meta": {...}}`.
- **Errors** — services/validators raise `DomainError` subclasses
  (`ValidationFailed` 400, `NotFound` 404, `PermissionDenied` 403, `Conflict` 409)
  that know **nothing about HTTP**. `exceptions.drf_exception_handler` is the
  single place any exception becomes `{"error": {"code", "message", "details",
  "request_id"}}`. Prefer raising these over returning DRF error responses. The
  `details` list is what makes a failed resource load useful — every problem at
  once, rather than the first one seven times.
- **Request IDs** — `middleware.RequestIDMiddleware` assigns each request a
  correlation id (honors inbound `X-Request-ID`), resolves the client IP, injects
  both into every log record the request causes, and echoes the id back.
- **Access log** — `middleware.AccessLogMiddleware` writes one line per request.
  The message is a *sentence* naming who called, what they asked for and what
  came back, not one of three fixed strings. `caller` separates people from
  machinery: a *passing* health probe logs at DEBUG (invisible at the default
  level), a failing one at WARNING.

### Logging — the logs name things, they don't number them

`shared.logging.get_logger` returns a `JSONLogger` taking custom fields as
keywords, each checked against `shared.logging.schema.SUPPORTED_LOG_FIELDS`, so
one concept keeps one key across the backend. Adding a field means adding it
there, with a comment on what it holds.

**Entities go in as labels, never as ids.** There is no `question_id` in the
schema: a line identified by a UUID can only be read with a database beside it.
`shared.logging.labels` turns a model into the name a person uses for it —
`labels.question(q)` is its slug, `labels.category(c)` its slug, `labels.user(u)`
the account's email. Every helper is `None`-safe, never imports an app, and never
triggers a query.

```python
from shared.logging import get_logger, labels

logger = get_logger(__name__)
logger.info("Questions synced", category=labels.category(category), summary=str(report))
```

`logger.violate(...)` is a custom level (35) for actions the platform *refused* on
authorization grounds, so "how often does someone try what they may not do?" is
countable apart from ordinary warnings.

### Realtime — the transport over Phase C's rules

`apps.matches` gets a WebSocket transport over the match engine Phase C already
tested without one. `config/asgi.py`'s `websocket` branch is wired: JWT off a
`?token=` query param (`authentication.JWTAuthMiddlewareStack` — the API has no
session cookie to reuse, and a browser `WebSocket` cannot set a header),
`AllowedHostsOriginValidator`, `apps.matches.routing`.

Two consumers, both thin (`consumers.py` — receive → validate → call a
`services` function → broadcast through `publish.py`), matching
`backend/CLAUDE.md`'s promise that the rules stay callable from a test with no
socket in sight:

- **`MatchmakingConsumer`** (`ws/v1/matchmaking/{category_slug}/`) — joins
  `apps.matches.pool`'s one-slot-per-category queue and waits for
  `events.MATCH_FOUND`. **The pool is `django.core.cache.cache`, not a
  hand-rolled Redis client** — the project already has exactly one story for
  "shared, ephemeral, per-process-or-real-Redis state" (`CACHES`, the same
  split `CHANNEL_LAYERS` draws), and pairing needs only *one* atomic
  primitive: `cache.add` as a mutex around a single waiting-player slot, which
  is enough because the pool never holds more than one waiter by construction
  — the second joiner is paired and both leave immediately.
- **`MatchupConsumer`** (`ws/v1/matches/{matchup_id}/`) — the live game.
  `events.ANSWER_SUBMIT` is the only write a client may send; everything else
  is server-decided and pushed. Each connected socket schedules its own
  watchdog (`_watch_question_timeout`) so a question nobody answers still
  closes on the server's clock, not the client's; `apps.matches.presence`
  (cache-backed, TTL'd) and a reconnect grace window
  (`constants.RECONNECT_GRACE_SECONDS`) are what let a mid-match refresh
  resume — `services.abandon_matchup` fires only once that window elapses
  with nobody back.

**A task spawned with `asyncio.ensure_future` and not held onto gets silently
garbage-collected mid-flight** — documented `asyncio` behaviour, and the bug
that took the longest to find while building this. `_WatchdogMixin._spawn` is
the one place every loose task (the watchdog, the abandon timer) is created,
specifically so it is held in `self._background_tasks` and this cannot
recur.

**A closing question can be closed by more than one caller at once** — the
second player's own `submit_answer` call, or either side's watchdog — and only
one may broadcast the result. `consumers._try_close_question`'s `cache.add`
mutex (the same primitive the pool uses) is what elects exactly one.

Without `REDIS_URL` both the channel layer and the cache fall back to
in-process backends, which is not a degraded Redis but a *per-process* layer:
correct for `runserver` and the test suite (`apps/matches/tests/
test_realtime.py`, driven with `channels.testing.WebsocketCommunicator`
against the real consumers — no shortcuts through `services`), wrong for any
container deployment with more than one replica.

**Never poll a `WebsocketCommunicator` with a short timeout hoping a miss is
harmless** — `asgiref`'s test harness cancels the underlying consumer task the
moment a wait times out. A timeout is "this socket is done," not "nothing yet,
ask again."

**Abuse limits on the paths that cost something** (`apps.matches.abuse`) — the
WebSocket half of the family `apps.accounts.services.lockout` started, same
posture (count first, refuse second, fail open), different mechanism: there is
no request/response cycle here for `ScopedRateThrottle` to hang a scope off, so
this reuses `apps.matches.pool`'s "one atomic counter behind whatever `CACHES`
is" primitive instead. Three limits, all keyed on the player id: how many
`events.ANSWER_SUBMIT` frames one player may send per window
(`check_answer_submit_rate`, checked in `MatchupConsumer.receive_json` before a
payload ever reaches `services.submit_answer`); how many times one player may
join a category's pool per window (`check_matchmaking_join_rate`, checked in
`MatchmakingConsumer.connect` before `pool.join_pool`); and a **budget**, not a
rate — how many sockets (matchmaking and matchup, added together) one player
may hold open at once (`register_socket`/`unregister_socket`, paired with
every `connect`/`disconnect`). A refusal at `connect` closes with
`CLOSE_RATE_LIMITED` (4429); a refusal mid-match sends `events.ERROR` with
`code="rate_limited"` rather than closing the socket, since a burst is not a
reason to end the game. `MATCH_ABUSE_LIMITS_ENFORCED` is off in the test
settings the way `LOGIN_LOCKOUT_ENFORCED` is — counted, never enforced, so
`test_realtime.py`'s own tight request loops do not trip a limit meant for
someone else; `apps.matches.tests.test_abuse` asks for it back with
`@override_settings`.

### ops — the admin's own door

`shared.admin_url.resolve_admin_url` already keeps the Django admin off
`/admin/` (`ADMIN_URL` is a random 40-character prefix unless one is
configured). `apps.ops` adds a second gate on top, for deployments that turn
`ADMIN_GATE_ENABLED` on (production defaults it to `True`; `local.py` leaves
it off — a solo developer has nobody else who could open it): the mounted
prefix 404s from *outside* no matter what it is, and the admin answers only
under a token minted by `manage.py open_admin --minutes 30`, stored hashed on
an `AdminWindow` row (`apps.ops.models`) and closed by `manage.py close_admin`
or its own clock.

A row rather than an environment variable, because opening the admin must not
restart a process every worker inherits differently, must be seen identically
by every worker in every replica, and should leave a record of who opened it
and when — `open_window`/`close_windows`/`window_for_token`
(`apps.ops.services`) are the one place that reasons about "live," so the
gate, the admin read-only listing (`apps.ops.admin`) and both commands share
one definition of it. The plaintext token exists exactly once, in the URL
`open_admin` prints; the row keeps only its SHA-256.

`apps.ops.middleware.AdminGateMiddleware` is the gate itself — mounted first
in `MIDDLEWARE`, above WhiteNoise, and removes itself via `MiddlewareNotUsed`
when `ADMIN_GATE_ENABLED` is off rather than checking a flag every request.
With it on: the admin's own static assets (`/_ops/static/…`, where
`STATIC_URL` moves to in production) are served only while *some* window is
live; the mounted `ADMIN_URL` prefix reached directly is an ordinary 404; and
`/_ops/<token>/…` is checked against the live window and, on a match,
rewritten — `path_info` loses the `/_ops/<token>` prefix and Django's script
prefix gains it, which is what makes `reverse()` (every admin link, every form
action, the login redirect) come back out carrying the token. A wrong token
and a closed window both answer with Django's ordinary 404, never a 403 — a
403 would confirm a right token exists.

**The live token never reaches a log line.** `shared.admin_url.redact_ops_path`
strips the token out of an `/_ops/<token>/admin/…` path, and
`apps.core_common.middleware.AccessLogMiddleware` applies it before the `path`
field (and the sentence built from it) ever reach the logger — the access-log
line for the very request that used the token must not become a second copy
of the credential. `apps.ops.tests.test_redaction` proves both the helper and
the real logged line.

### Container and deploy

One image (`backend/Dockerfile`, build context the **repository root** —
`docker build -f backend/Dockerfile .`), two roles picked at runtime by
`SERVER_MODE`, both branched in `entrypoint.sh`:

- `api` (default) — `gunicorn` on `config.wsgi`, `gthread` workers (the
  workload is DB-I/O bound, so a thread picks up the next request while
  another blocks rather than a sync worker serving nothing meanwhile).
- `realtime` — `uvicorn` on `config.asgi`, one process, scaling by
  concurrency rather than worker count — sockets are cheap to hold and
  expensive to drop. Neither server is an app dependency (local `runserver`
  uses Daphne, already in `INSTALLED_APPS` for that reason); both are
  installed straight into the builder-stage venv in the Dockerfile.

Only `api` migrates, and only with `manage.py migrate_locked`
(`apps.core_common.management.commands.migrate_locked`) rather than plain
`migrate`: it takes a Postgres advisory lock first (`LOCK_KEY`, fixed), so
replicas starting together serialise instead of racing the same migration —
the second one waits, then finds nothing left to do. On SQLite (no advisory
locks, no real concurrency) it degrades to a plain `migrate`. `RUN_MIGRATIONS=0`
turns this off for a platform that migrates from an init container instead.

The **same image** runs both roles, which is what keeps them from ever being
built off different commits — a live matchup depends on `apps.matches` code
`config.wsgi` and `config.asgi` agreeing on, and two images built separately
could drift.

`collectstatic` runs at **build time**, as root, before `USER app` drops
privileges and the code dir becomes effectively read-only — the admin's own
CSS/JS is the only static this backend has, and doing this at container
startup would mean writing into a directory the runtime user cannot write to.
Runtime-writable state (a fallback SQLite file if no external `DATABASE_URL`
is given, MEDIA_ROOT's default location — see step 23) lives on the `/data`
volume instead, which is why the entrypoint `cd /data` before starting either
server (`PYTHONPATH=/app` keeps `config.wsgi`/`config.asgi` importable
regardless of cwd).

Health probes point at the two endpoints from `apps.core_common.api.views`
that already existed for this (`/api/v1/health/live/`, never touches the
database — a liveness failure gets the container *killed*, so anything it
checked becomes something that can restart every replica at once;
`/api/v1/health/ready/`, does check the database — a pod with no database
should stop receiving traffic, not be shot). The Dockerfile's own
`HEALTHCHECK` hits `health/live/` with nothing but the stdlib. `production.py`
exempts `^api/v1/health/` from `SECURE_SSL_REDIRECT`
(`SECURE_REDIRECT_EXEMPT`) — a probe hits the pod directly over plain HTTP,
bypassing the ingress that would otherwise set `X-Forwarded-Proto`, and
without the exemption every probe hit is a 301 a *liveness* check reads as
dead.

`MEDIA_ROOT` (question images, and later avatars) defaults to `BASE_DIR /
"media"` in `base.py` — correct for local dev, wrong for the container's code
dir — and `production.py` overrides the default to `/data/media`: the same
`/data` volume the Dockerfile already creates for a fallback SQLite
`DATABASE_URL`, so `sync_questions` (`apps.questions.services.sync`) has
somewhere durable to copy images into with no operator having to point
`MEDIA_ROOT` anywhere themselves. Still overridable by the `MEDIA_ROOT` env
var either way — a mounted object store is a path like any other.
`apps.core_common.tests_media_root` shells out to a fresh interpreter to
prove the default (importing `config.settings.production` in-process would
run it against the test settings' already-configured Django, not a clean
one).

### Journey logging and the load rehearsal

**"How many matches completed, and how long did players wait for an
opponent?" is a log query, not a guess.** Four moments in a match's life
each write one `INFO` line with `action` set to a fixed, queryable verb — a
sentence for a human tailing the log, a stable field for a query against it,
the same split `AccessLogMiddleware` already draws:

- **`action="queued"`** — `MatchmakingConsumer.connect`, the instant a
  player becomes the one waiting.
- **`action="matched"`** — `consumers._pair`/`_pair_with_bot`, with
  `duration_ms` set to how long the *other* side had been waiting
  (`pool.Pairing.opponent_queued_at`, now carried in the pool's cached
  waiting slot alongside the player id) — this side's own wait was ~0, since
  its join is what completed the pairing.
- **`action="answered"`** — `services.submit_answer`, `duration_ms` the
  server-measured response time; correctness lives in the sentence, not a
  field of its own — there is no boolean on the schema for a fact the
  message already states, and adding one would be the second spelling
  `shared.logging.schema` exists to prevent.
- **`action="completed"`** — `services._log_match_completed`, called from
  both `complete_matchup` and `abandon_matchup` (either is a matchup
  reaching the same terminal state), `duration_ms` the whole match's
  wall-clock length and `player` the winner's label when there is one.

`apps.matches.tests.test_journey_logging` reads every one of these back with
`assertLogs`, filtering on `action` the way an operator's query would —
including the two written from real sockets (`queued`/`matched`), driven
over an actual `WebsocketCommunicator`, not asserted against the service
layer standing in for the transport.

**`manage.py load_rehearsal`** (`apps.matches.management.commands`) rehearses
what steps 22–24 shipped — the real gunicorn/uvicorn processes, the real
Redis pool, real concurrent load — which nothing calling `apps.matches
.services` directly can prove. N simulated players, each a real account
(`POST /auth/registration/`), a real matchmaking socket and a real matchup
socket, answering at a randomised "human" delay rather than a test's instant
call. Needs the `dev` dependency group (`httpx`, `websockets` — neither
ships in the runtime image) and runs against `--base-url`, never in-process.
Every account it creates is tagged in its email
(`loadrehearsal-<run>-<n>@rehearsal.invalid` — `.invalid` is RFC 2606's
reserved-forever TLD, so nothing here can misfire against a real inbox).
`manage.py load_rehearsal_teardown --run <run>` removes exactly those
accounts and nothing else — **not** the `Player` rows or the matches they
played: `MatchupPlayer.player` is `PROTECT`, the same guard that keeps
anyone's match history from disappearing under them, and a rehearsal account
earns no exception to a rule written for exactly this reason. See both
commands' docstrings before running either against anything but a
disposable environment.

## Conventions

- Service/selector/validator functions use **keyword-only args**
  (`def f(*, category, count)`).
- DRF defaults (`config/settings/base.py`): `IsAuthenticated` by default (opt out
  per-view with `AllowAny`), URL-path versioning (`v1`), page size 25, throttling,
  and `django_filters` + ordering/search backends enabled globally.
- **The API authenticates by Bearer token only** — `SessionAuthentication` is
  deliberately absent, so a leftover Django-admin `sessionid` cookie cannot
  authenticate an API call and then demand a CSRF token.
- New domain apps go in `apps/`, are added to `LOCAL_APPS` in `base.py`, and get
  their `api/urls.py` included in `config/urls.py` under `api_v1_patterns`.
- **The suite runs on SQLite and production runs on PostgreSQL**, so anything
  written against a Postgres-only feature passes review and breaks on deploy —
  or, worse, breaks locally and passes CI. `JSONField`'s `contains` lookup is the
  one already hit: `tags__era="2000s"` (a key path) means the same as
  `tags__contains={"era": "2000s"}` for a flat dict and works on both backends,
  which is why `selectors.available_questions` filters that way. A key path
  addresses a *key*, so a digit in it would address an array index instead —
  hence the guard on tag keys.
