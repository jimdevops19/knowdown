# knowdown

The 2026 solution for trivia.

Knowdown is a real-time 1v1 trivia game. Everyone online sits in one global
matchmaking pool; two players get paired, race through 3, 5 or 7 questions, and
the fastest correct answer takes each one. Winner and loser go back into the
pool with their rating updated. NBA first — the architecture keeps categories
independent of question types so the same engine can run other sports later.

`initial-plan.md` is the full product and architecture plan.

## Repo layout

```
pyproject.toml, uv.lock       # Python 3.13, managed with uv
backend/                      # the Django project — see backend/CLAUDE.md
  apps/questions/resources/   # every question, as YAML
scripts/                      # bootstrap + asset generation
```

## Running it

Zero-config: with no `.env` it runs against local sqlite with in-memory caching,
so this is the whole of it.

```bash
uv sync

cd backend
uv run python manage.py migrate
uv run python manage.py sync_questions     # load the question catalog
uv run python manage.py runserver
```

Then `GET http://127.0.0.1:8000/api/v1/categories/`, with the API docs at
`/api/docs/` and health at `/api/v1/health/`. `runserver` prints the admin URL it
picked — the admin is never at `/admin/`.

Copy `.env.example` to `.env` at the repo root to point it at PostgreSQL and
Redis.

```bash
uv run python manage.py test --settings=config.settings.test
```

## Writing questions

Questions live in `backend/apps/questions/resources/` — `categories.yaml`, plus a
folder of YAML per category — and are loaded with:

```bash
uv run python manage.py sync_questions --dry-run   # validate, report, write nothing
uv run python manage.py sync_questions
```

The load is idempotent and keyed on each question's `slug`, so **editing a
question is editing its YAML and re-running**: the row is corrected, not
duplicated, and every player's history against it survives. A question removed
from the files is deactivated rather than deleted, because a match that already
played it is a match that happened.

Each file opens with a comment block explaining its question type and every field
it takes; `resources/nba/single-answer.yaml` documents the fields common to all
of them. Start there.

## Where things are

- `backend/CLAUDE.md` — how the backend is put together and why.
- `initial-plan.md` — where it is going.
