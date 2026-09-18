# Scoring

Knowdown scores an answer in two independent steps, owned by two different
domains, and this split is deliberate:

1. **`apps.questions.services.evaluation.evaluate_answer`** decides *how right*
   an answer was. It returns an `AnswerResult` with two fields — `is_correct`
   (a strict yes/no) and `score` (credit, a float from `0.0` to `1.0`, the
   fraction of the question the player actually got right). This step knows
   nothing about points, speed, or what a question is "worth."
2. **`apps.matches.constants.score_answer`** turns that credit into points,
   factoring in how fast the player answered relative to the question's own
   clock. This step knows nothing about how correctness was determined for
   any particular question type — it just multiplies.

Every question type on the platform funnels through both steps. What differs
between types is **only step 1** — how credit is computed — plus one type
that opts out of the speed multiplier in step 2.

## The points formula (step 2, shared by every type)

```
if credit <= 0:
    points = 0
elif question_type not in SPEED_SCORED_TYPES:      # name-as-many only
    points = round(MAX_QUESTION_POINTS * credit)
else:
    remaining_fraction = max(0, (time_limit_ms - response_time_ms) / time_limit_ms)
    speed_factor = MIN_SPEED_FACTOR + (1 - MIN_SPEED_FACTOR) * remaining_fraction
    points = round(MAX_QUESTION_POINTS * credit * speed_factor)
```

Where `MAX_QUESTION_POINTS = 100` and `MIN_SPEED_FACTOR = 0.5`. A wrong
answer is worth nothing no matter how fast it arrived — speed only
multiplies credit that already exists, so guessing quickly is never better
than answering correctly slowly. A correct answer submitted with no time
left still keeps half its value (the `0.5` floor), so a hard question worked
out right at the wire is not scored like a coin flip. `response_time_ms` is
always measured by the server, never reported by the client, which is what
keeps a patched client from lying about its own stopwatch to win a race it
lost.

Almost every question type is **speed-scored**: answering sooner is worth
more, all the way up to the full 100 points for an instant, fully-correct
answer. **`name-as-many` is the one exception** (see below) — its clock is a
budget to spend, not a deadline to beat, so paying more for answering fast
would reward stopping early.

## Question types and their credit formulas

The platform has nine question types, sharing one evaluator each
(`ANSWER_EVALUATORS` in `apps/questions/services/evaluation.py`). Eight of
them are **all-or-nothing or all-or-the-matching-set** — credit is either
`0.0` or `1.0`, and the interesting cases are the two that award partial
credit, plus the one that pays for rarity.

### Single answer / image answer

One option id, checked against the question's own set of options — the two
share an evaluator because a picture-as-option changes only how the client
draws it, not what the claim being scored is. Credit is `1.0` if the chosen
option is flagged correct, `0.0` otherwise. There is no partial credit: it
is one indivisible claim ("this one"), so points are `100 × speed_factor`
for a right pick and `0` for a wrong one.

### Multiple answer

The player submits a set of option ids, and credit is `1.0` only if that set
is an **exact match** for the question's correct options — extra picks are
just as wrong as missing ones. Per-option credit is deliberately not
offered: it would make selecting every option a winning strategy, and
"select all that apply" stops being the question being asked the moment a
shotgun answer scores anything. Like single-answer, this collapses to
`0.0`/`1.0`, so points are `100 × speed_factor` or `0`.

### True/false

The simplest evaluator: credit is `1.0` if the submitted boolean equals the
question's stored answer, `0.0` otherwise. Points follow the same
`100 × speed_factor` / `0` split as every other all-or-nothing type.

### Free text

The submitted text is normalized (case, punctuation, whitespace) and
checked against a set of accepted spellings authored per question, rather
than fuzzy-matched against one canonical string — fuzzy matching would mean
the platform deciding on the player's behalf how wrong a spelling is allowed
to be, a threshold nobody can defend if it costs someone a match. Credit is
`1.0` for any accepted spelling, `0.0` otherwise. All-or-nothing, same
points formula.

### Ordering

The player submits a full permutation of the question's items, compared
position by position against the authored order. Credit is `1.0` only if
every position matches; `0.0` for anything else, including transpositions —
half a correct ordering is not half an answer, it is a different
arrangement. A submission that is not a genuine permutation of the
question's items (one item missing, one repeated, one invented) is not
scored at all — it is refused as malformed, the same way a client sending
nonsense is treated everywhere else in the platform.

### Matrix (grid)

The one authored type with real **partial credit**. A matrix question is a
grid of row × column intersections, and the denominator is the cells the
question actually *authored* — not `rows × columns` — because the grid is
sparse and a player is only asked to fill the intersections somebody has a
fact about:

```
credit = matched_cells / authored_cells      # capped implicitly, matched ≤ authored
```

Each cell can accept several right answers (e.g., "a player who played for
both these teams" has as many correct names as the rosters share), and any
one of them fills the cell. A `kind: teams` grid answers the same shape of
question from the roster data itself rather than from hand-authored
answers, but the credit formula is identical either way — same denominator,
same per-cell scoring.

Notably, `probability_score` (a 2–10 "how obscure is this pick" grade
authored per accepted name) is **never read here**. Two players who both
fill the grid correctly score identically regardless of how obscure their
picks were — paying more for a rarer name would make otherwise-equal
answers score differently, which this type doesn't do (name-as-many, below,
is the one place that rarity is paid for). Points are
`100 × credit × speed_factor`, so a player who fills 7 of 9 cells scores
about 78% of what a full grid would earn, scaled further by how fast they
answered.

### Gradual hints

Also **per-field partial credit**, for the same reason as a matrix: a
question like "guess the game" (year, round, game number) is genuinely
several sub-claims, and someone who nails two of three fields knew most of
it.

```
credit = matched_fields / authored_fields
```

The denominator is the fields the question *asks for*, never the fields the
player chose to fill in — otherwise answering one of three boxes and
leaving the rest blank would be a perfect answer. Each field is scored like
a miniature free-text answer (folded/normalized, checked against accepted
spellings for that field). How many of up to five hints a player waited for
before answering is **not** factored into credit at all — that's already
priced in by response time in the points formula, and pricing it twice
(once in credit, once in speed) would be the questions domain deciding what
a question is worth, which isn't its job. Points: `100 × credit ×
speed_factor`.

### Name as many

The one type with **no fixed board and no options at all** — the question
is a stat line ("name as many players with 1,000+ career threes"), and
"the board" is every NBA player who ever qualified, looked up from a baked
career-stats artifact at scoring time. It is also the **only type where
`probability_score`/rarity is paid for**, and the **only type exempt from
the speed multiplier**.

```
earned = sum(player.probability_score for name in submitted_names if name qualifies)
credit = min(1.0, earned / question.target_score)
points = round(100 * credit)          # no speed_factor
```

Three rules make this shape work:

- **A name that doesn't qualify is worth nothing, but is not malformed** —
  unlike every authored type, there's no such thing as "not one of the
  options" here, since the player was invited to name anybody. Nothing is
  deducted for a wrong guess either, because a mode that punished guesses
  would reward the opposite of what it's testing: how many you can recall.
- **The denominator is `target_score` (an author-set target), not the whole
  board.** Every qualifying player is worth points and nobody types
  hundreds of names, so scoring against the entire board would make full
  credit unreachable.
- **Credit caps at `1.0`.** Beating the target answers the question fully;
  there's no bonus for going further.

Speed is excluded on purpose: the clock here (typically 30s) is a *budget to
spend*, not a *deadline to beat*. If speed multiplied points the way it does
elsewhere, a complete answer submitted at 1 second would outscore the same
answer at 29 seconds — paying players to stop typing early, which is the one
strategy this mode must never reward. The race is still real: both players
get the same clock, and whoever names more (weighted by rarity) in that time
wins.

## The popularity score (`probability_score`)

Every accepted name across the catalog — matrix-cell answers and the
career-stats artifact `name-as-many` reads from — carries a
**`probability_score`**, a hand-graded integer from **2 to 10** meaning "how
obvious is this pick": Michael Jordan for a Bulls×Wizards matrix cell is a
`2` (nearly everyone gets it); a one-season backup who happens to satisfy
the same cell is a `10` (only a real expert would think of them). Ungraded
answers default to `DEFAULT_PROBABILITY_SCORE = 5`, the deliberate midpoint
meaning "nobody has graded this yet."

Despite being authored on almost every answer in the catalog, this score is
**read in exactly one place**: `name-as-many`'s credit formula above, where
`earned` sums each qualifying name's `probability_score` rather than
counting names 1-for-1. Everywhere else — matrix cells in particular — the
score is authored (because grading obscurity is a judgment call only a
question author can make, and it's cheaper to grade as you write than to
grade a whole catalog after the fact) but never spent: two players who both
fill a matrix grid correctly must score identically, and letting a rarer
name pay more would break that guarantee. The score also never reaches a
client's board while the question is live — a grid whose accepted answers
are all `9`s or `10`s would itself be a hint about how hard the cell is.

**Why this design:** `name-as-many` is the one type whose "board" has no
ceiling — every qualifying player in NBA history is a valid guess — so
"how deep did you go" *is* the question. A flat rate per name would turn the
mode into "type the five most famous names and stop"; weighting by rarity
via `probability_score` rewards depth of recall instead of just breadth of
fame.

## Reference: where this lives in code

| Concern | Location |
| --- | --- |
| Credit per question type | `backend/apps/questions/services/evaluation.py` (`ANSWER_EVALUATORS`) |
| Points from credit + speed | `backend/apps/matches/constants.py` (`score_answer`, `MAX_QUESTION_POINTS`, `MIN_SPEED_FACTOR`, `SPEED_SCORED_TYPES`) |
| Popularity/rarity grading | `backend/apps/questions/models` (`probability_score`, `DEFAULT_PROBABILITY_SCORE`) and `backend/apps/questions/career_stats.py` |
| Question time limits | `backend/apps/matches/constants.py` (`FALLBACK_QUESTION_TIME_LIMITS_MS`, `time_limit_ms_for`) |
| Ladder rating (Elo) | `backend/apps/rankings/services/ratings.py` |
| Board draw / exposure bias | `backend/apps/questions/selectors/__init__.py` (`select_questions`), `backend/apps/exposure/selectors/__init__.py` (`pick_least_exposed`) |

## Two other kinds of "scoring" on the platform

These aren't part of the per-question credit/points formula above, but they're
adjacent enough to be worth distinguishing:

**Which questions make it into a matchup.** `select_questions` draws the
board once per matchup from the category/level-band pool, but not uniformly —
`apps.exposure.selectors.pick_least_exposed` sorts the candidate pool so that
whichever question either player has seen most often sorts last, biasing the
draw toward questions neither side has answered before. This has no interaction
with point values; it only affects which questions are asked.

**The per-category ladder rating**, separate from any single matchup's points.
`apps.rankings.services.ratings` runs a standard Elo update once per finished
matchup:

```python
K_FACTOR = 32
DEFAULT_PLAYER_RATING = 1000

expected = 1 / (1 + 10 ** ((opponent_rating - rating) / 400))
new_rating = round(rating + K_FACTOR * (actual_score - expected))
```

`actual_score` is `1` for a win, `0` for a loss, `0.5` for a tie, applied
symmetrically to both players. A matchup against a CPU bot is never rated
(`Matchup.is_ranked` is `False` whenever either side is a bot), so bot games
score points and award achievements normally but never move the ladder.
