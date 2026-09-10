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
  and `GET/PATCH /players/me/`.
- **`apps/core_common`**, **`shared/`** — the platform-wide contracts (below).
- **`apps/matches`, `apps/rankings`, `apps/achievements`** — **scaffolds**.
  Directory layout and an `AppConfig`, no models. The tables in
  `initial-plan.md` land with the increment that uses them.

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

### Realtime — configured, not yet built

`CHANNEL_LAYERS` and `config/asgi.py` are in place with only the `http` branch
wired. The intent (`initial-plan.md`): **Redis + Channels hold who is online and
what is happening right now; PostgreSQL stores what happened.** The matchmaking
pool is one logical queue, not a database room per player, and the server owns
the clock — the client displays a timer, the server decides who answered first.
Without `REDIS_URL` the channel layer falls back to an in-memory one, which is
not a degraded Redis but a *per-process* layer: correct for `runserver` and the
test suite, wrong for any container deployment.

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
