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
  the authored YAML, `sync_questions`, and the selection seam the match engine
  will call.
- **`apps/categories`** — the `Category` model and a read-only endpoint pair.
- **`apps/accounts`** — the `User` model only. No sign-in, no JWT endpoints, no
  OAuth yet; it exists now because `AUTH_USER_MODEL` cannot be swapped after the
  first `migrate` without pain.
- **`apps/core_common`**, **`shared/`** — the platform-wide contracts (below).
- **`apps/players`, `apps/matches`, `apps/rankings`, `apps/achievements`** —
  **scaffolds**. Directory layout and an `AppConfig`, no models. The tables in
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
```

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
once, the admin reads it to register them. Adding a question type is: a model, a
`QuestionType` member, a schema variant, and **one line in the registry**.

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
- **Selection lives in `questions`, not in `matches`.** The match engine must stay
  independent of the concrete question type, so "give me five NBA questions" is a
  question this domain answers (`selectors.select_questions`) and the match domain
  merely asks. Answer *evaluation* belongs here too and is not written yet.

Positions and orders (`option.order`, `correct_position`, matrix row/column
`order`) are **derived from the list order in the YAML**, never authored — which
is why no resource file can have a gap or a duplicate position.

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
