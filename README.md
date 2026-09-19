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
uv run python manage.py sync_rooms         # load the lobby (rooms) — after the catalog
uv run python manage.py runserver
```

Then `GET http://127.0.0.1:8000/api/v1/rooms/`, with the API docs at
`/api/docs/` and health at `/api/v1/health/`. `runserver` prints the admin URL it
picked — the admin is never at `/admin/`.

Copy `.env.example` to `.env` at the repo root to point it at PostgreSQL and
Redis.

```bash
uv run python manage.py test --settings=config.settings.test
```

## Defining rooms

A **room** is the set of settings a match is played under — which categories the
board is drawn from, narrowed by which tags, and how many questions a match
there runs — and it is what a player picks, in place of a bare category. Rooms
live in `backend/apps/rooms/resources/rooms.yaml`:

```yaml
- name: Ring Chasing
  slug: nba-room-finals
  questions_asked_ranges: [4, 5, 6]   # one is drawn per match
  categories:
    - slug: nba
      filter_tags:
        topic: finals                 # omit for the whole category
```

```bash
uv run python manage.py sync_rooms --dry-run
uv run python manage.py sync_rooms
```

Loaded the same way questions are: idempotent, keyed on `slug`, and a room
dropped from the file is deactivated rather than deleted. Run it *after*
`sync_questions` — a room names categories that have to already exist. The
first category listed is what a match there is filed under, since a rating is
per category and a matchup carries exactly one.

A room drawing from a **single** category is rated: every question asked
belongs to the ladder the result moves. A room that lists **two or more** is
played unrated — a result can only move one ladder, and scoring the first
category for questions that came from the second would be a lie. The lobby
says so on the room before anybody joins it.

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
