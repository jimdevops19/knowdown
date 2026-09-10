---
name: prepare-questions
description: Author or edit Knowdown trivia questions by hand-editing the YAML files under apps/questions/resources/. Use whenever the task is "write N questions about X", "add a question to category Y", "fix/rephrase question <slug>", or "add a new category" — anything whose deliverable is question content, not code. Loads the pydantic schema rules for each of the seven question types so the YAML it writes loads cleanly on the first try.
---

# Preparing questions

Your only job when this skill is active: **edit the right YAML file(s) under
`apps/questions/resources/`** to add, change, or retire question content. You
are not writing Python. Do not touch `models/`, `schemas/`, `services/`,
`selectors/`, migrations, or any other code in this repo as part of this task
— if the request needs a code change (a new question *type*, a new field, a
scoring rule), that is a different job; say so instead of improvising it here.

Read the target file(s) before editing them — every file in
`apps/questions/resources/` opens with a comment block documenting its own
fields, and the ones read into this skill below are a condensed version of
the same rules, kept here so you don't have to re-derive them from
`apps/questions/schemas/__init__.py` each time. Match the surrounding
questions' tone, tag vocabulary, and comment style; append new entries at the
end of the `questions:` list unless asked to edit or reorder specific ones.

## Where things live

```
apps/questions/resources/
  categories.yaml          # the list of categories (slug, name, description, is_active)
  <category-slug>/
    single-answer.yaml
    image-answer.yaml
    multiple-answer.yaml
    true-false.yaml
    free-text.yaml
    ordering.yaml
    matrix.yaml
    images/                # binaries referenced by `image:` fields in this category
```

One file per question **type**, per category — never mixed. `nba` is the only
category today. Adding a new category is: an entry in `categories.yaml` plus a
new folder named after its `slug`, containing whichever of the seven type
files you're populating (a type file with no questions yet simply doesn't
exist until there's something to put in it — don't create empty ones).

**Categories:**

```yaml
- slug: nba                # ^[a-z0-9]+(-[a-z0-9]+)*$, permanent — the folder
                            # name, the API path, the scope of a rating
  name: NBA
  description: >-
    A short pitch for the category.
  is_active: true          # false takes it out of matchmaking without deleting it
```

## Fields every question carries

| field | rule |
|---|---|
| `slug` | `^[a-z0-9]+(-[a-z0-9]+)*$`, ≤120 chars. The upsert key — **unique across every question file and every type**, not just within one file. Changing it retires the old question and creates a new one; fixing a typo in wording never should. Prefix with the category (`nba-...`) by convention. |
| `description` | non-empty. The question as the player reads it. |
| `level` | integer 1–10. See "picking a level" below. |
| `tags` | `dict[str, str]`, free-form. Keep keys consistent within a category (`topic`, `era` are what `nba` already uses) or a themed-round filter finds nothing. |
| `image` | optional filename (not a path) in `<category>/images/`. Illustrates what's being asked — **not** the answer; that's `image-answer`'s `options`. Missing file fails the load. |
| `time_limit_seconds` | optional, 1–600. Overrides the type's default time limit for just this question. Leave unset unless a question is unusually fiddly. |

Unknown keys are a load error, not a silent default — don't invent field
names, and don't leave a typo'd key behind.

### Picking a level

Bands (`apps/questions/constants.py`, `LEVEL_BANDS`): **easy 1–3, medium 4–7,
hard 8–10**. Matchmaking draws whole matches from one band, so the level you
pick determines who this question gets shown to — a level should reflect how
hard the *fact* is to know, not how tricky the phrasing is. For `true-false`
specifically: a 50/50 guess is worth half a mark by construction, so a claim
that's genuinely a coin flip is never a level 1 — reserve low levels for
claims that are obviously true or false to anyone who follows the sport, and
spend the higher levels on claims that sound wrong and are right (or vice
versa).

## The seven types

Every type file's own header comment has the full rationale; this is the
load-time contract.

**`single-answer`** — a list of text options, exactly one correct.
```yaml
- type: single-answer
  slug: nba-most-championships-franchise
  description: Which franchise has won the most NBA championships?
  level: 3
  tags: {topic: teams, era: all-time}
  options:
    - {text: Boston Celtics, is_correct: true}
    - {text: Los Angeles Lakers}
    - {text: Chicago Bulls}
    - {text: Golden State Warriors}
```
≥2 options, exactly one `is_correct: true`. Authored order is fine — the
client shuffles per matchup before showing them.

**`image-answer`** — same shape, but the options *are* pictures.
```yaml
- type: image-answer
  slug: nba-identify-free-throw-line
  description: Which diagram marks the free-throw line?
  level: 1
  tags: {topic: rules, era: all-time}
  options:
    - {image: court-free-throw-line.png, is_correct: true}
    - {image: court-three-point-line.png}
    - {image: court-baseline-line.png, label: "optional alt text"}
```
≥2 options, exactly one correct, every `image` a distinct filename that
actually exists in `<category>/images/` (drop the asset there first, or ask —
don't invent a filename you haven't placed). Omit `label` where naming the
option would give the answer away.

**`multiple-answer`** — several options are right.
```yaml
- type: multiple-answer
  slug: nba-players-with-mvp-and-finals-mvp
  description: Which of these players have won BOTH MVP and Finals MVP?
  level: 5
  tags: {topic: awards, era: all-time}
  options:
    - {text: LeBron James, is_correct: true}
    - {text: Michael Jordan, is_correct: true}
    - {text: Tim Duncan, is_correct: true}
    - {text: Allen Iverson}
    - {text: Charles Barkley}
```
≥3 options, **at least 2** correct and **at least 1** wrong — one correct
option is a single-answer wearing the wrong type; every option correct means
"select all" has no wrong answer to avoid. Aim for a mix a knowledgeable fan
has to actually think about, not eliminate by obviousness.

**`true-false`** — the whole answer is a bool, no options list.
```yaml
- type: true-false
  slug: nba-jordan-drafted-third
  description: Michael Jordan was selected third overall in the 1984 NBA Draft.
  level: 4
  tags: {topic: draft, era: 1980s}
  answer: true
```
Write it as a **statement to agree or disagree with**, never phrased as a
question ("Was Jordan drafted third?" reads like it wants a number).

**`free-text`** — the player types the answer.
```yaml
- type: free-text
  slug: nba-most-assists-career
  description: Who holds the NBA record for the most career assists?
  level: 4
  tags: {topic: records, era: all-time}
  accepted_answers:
    - John Stockton
    - Stockton
```
≥1 accepted answer, matched case-insensitively — so the same spelling twice
in different cases is a load error, not two entries. List the **short
forms** a player racing a clock would actually type (surname, nickname,
jersey spelling), not just the full formal name. Don't use this type where
the right answer has an open-ended number of phrasings — that's a
`single-answer` in disguise.

**`ordering`** — items authored *already in their correct order*.
```yaml
- type: ordering
  slug: nba-order-bulls-finals-opponents
  description: >-
    The Chicago Bulls beat a different opponent in each of their first five
    championship runs.
  instruction: Order the opponents by the season the Bulls beat them, earliest first.
  level: 7
  tags: {topic: finals, era: 1990s}
  items:
    - Los Angeles Lakers
    - Portland Trail Blazers
    - Phoenix Suns
    - Seattle SuperSonics
    - Utah Jazz
```
≥3 distinct items. `instruction` is the direction ("earliest first",
"most to fewest") — keep it out of `description`, players miss a direction
buried in the question. **Positions are never authored**, the list order
*is* the answer — never add a `position:` key. Pick facts with an
unambiguous, non-drifting order: retired-player career totals and dated
events are safe; "best" anything, or an active player's still-climbing
total, is not.

**Never make the items bare years or numbers in sequence** (`1991, 1992,
1993, 1996, ...`). Sorting numbers takes no trivia knowledge at all — it's
answerable by anyone who can count, which defeats the point of asking. If the
underlying fact is "in what order did these years happen," name the thing
that happened each year instead (the opponent beaten, the award won, the
record broken) and let the year be the fact the player has to *know*, not a
number sitting in front of them already in order. The Bulls example above is
the fix for exactly this mistake — see `apps/questions/resources/nba/
ordering.yaml`'s header comment for the same rule in place.

**`matrix`** — name the thing where a row and a column meet.
```yaml
- type: matrix
  slug: nba-matrix-played-for-both-east
  description: Name a player who spent time with both franchises.
  level: 7
  tags: {topic: players, era: 2000s}
  rows: [Miami Heat, Chicago Bulls]
  columns: [Washington Wizards, Boston Celtics]
  cells:
    - row: Chicago Bulls
      column: Washington Wizards
      answers:
        - {answer: Michael Jordan, probability_score: 2}
        - {answer: Bobby Portis, probability_score: 5}
        - Jerian Grant                 # shorthand: probability_score 5
    - row: Miami Heat
      column: Boston Celtics
      answers:
        - {answer: Ray Allen, probability_score: 5}
```
≥2 rows, ≥2 columns, both lists of distinct titles. `cells` are **sparse** —
write only the intersections that have an answer, never every cell, and
never a `row_count`/`column_count` (those are derived). Every cell names its
row/column **by title, not index** — a title the file doesn't declare in
`rows`/`columns` fails the load, as does naming the same (row, column) pair
twice.

**A cell holds every answer that fills it, not one.** `answers` is a
non-empty list, and any entry on it takes the cell at evaluation time
(compared case- and whitespace-insensitively, like `free-text`). Two entries
differing only in case are one answer written twice and fail the load. So
write **all** of them: a "played for both these teams" square is satisfied by
everybody the two rosters share, and leaving names off makes the question
wrong rather than merely shorter.

`probability_score` is 2..10 — how obscure the pick is. 2 is the name
everybody says (Michael Jordan for Bulls x Wizards); 10 is the one only
somebody who watched that roster reaches for. Grade it if you can judge it;
otherwise write the bare-string shorthand, which means 5, and leave the
grading to whoever knows the sport. **Nothing scores with it yet** — a cell is
right or it is not, and credit is the fraction of the grid filled correctly —
so it is never a reason to leave an answer out.

## Workflow

1. Identify the category and type from the request; open the matching file
   (`apps/questions/resources/<category>/<type>.yaml`). If it doesn't exist
   yet, create it following the header-comment convention of its siblings —
   copy the tone of an existing type file in the same category, not a
   generic template.
2. Check every new `slug` isn't already used anywhere under
   `apps/questions/resources/` (grep across the whole tree, not just the file
   you're editing — the uniqueness constraint is global).
3. Write the entries per the shape above, in place, preserving the file's
   existing formatting style (inline `{text: ..., is_correct: true}` maps,
   `tags: {topic: ..., era: ...}`, etc.).
4. If asked to validate, or before handing off a large batch, run a dry run —
   it parses and cross-checks without writing anything:
   ```bash
   uv run python manage.py sync_questions --dry-run --category <slug>
   ```
   Fix whatever it reports and re-run; don't guess past a validation error.
5. **Do not run `sync_questions` without `--dry-run`** unless the user
   explicitly asks you to load the questions into the database — writing the
   YAML is the deliverable, loading it is a separate, explicit step.

## Retiring a question

Never delete a question's own history by hand-editing another table — the
loader is what does this. To retire one, delete its entry from the YAML (or
flip its category's `is_active: false` in `categories.yaml` to retire the
whole category); the next real `sync_questions` run deactivates the row
rather than deleting it, because a matchup that already played it still
points there. That's a code-owned mechanism, not something to try to emulate
by editing another file.
