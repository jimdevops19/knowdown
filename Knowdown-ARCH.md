# CPU (bot) opponents — architecture

## What this is

Matchmaking normally waits for a second human. This feature gives it a
fallback: if nobody else joins a category's pool within **8 seconds**, the
waiting player is paired against one of **50 seeded CPU players** instead of
waiting indefinitely.

- Each bot has a fixed **guessing probability between 30% and 90%** (how
  often it deliberately answers correctly).
- Each bot has a fixed **response-speed band spanning ~20% to ~90% of the
  question's own clock** (how much of the allotted time it lets pass before
  submitting) — a percentage, not a fixed number of seconds. See "Speed is a
  percentage of the clock, not a fixed number of seconds" below for why.
- The whole feature is behind one flag: **`FF_ENABLE_BOTS_IF_TIMEOUT`**. Off,
  none of this code path is ever reached — a lonely player simply keeps
  waiting, exactly like today.

| Setting | Env var | `config.settings.local` | Every other tier |
| --- | --- | --- | --- |
| Feature flag | `FF_ENABLE_BOTS_IF_TIMEOUT` | `True` (hardcoded) | `False` (default) |
| Timeout | `MATCHMAKING_BOT_TIMEOUT_SECONDS` | `8` (default) | `8` (default) |

`local.py` hardcodes the flag on regardless of the environment — a solo
developer running just this one process has nobody else to be matched
against, so leaving it off by default would make matchmaking hang forever in
the exact environment it needs to work zero-config in. Every other tier
(`test.py`, `production.py`) inherits `base.py`'s default of `False` and must
opt in explicitly via the environment, the same posture `LOGIN_LOCKOUT_ENFORCED`
and `MATCH_ABUSE_LIMITS_ENFORCED` already take for their own tier split. A
bot opponent still awards achievements and appears in match history exactly
like a human one, but never moves a rating (see "Bots are never ranked"
below) — nothing about the feature as a whole is a "test mode" default that
should leak into a real deployment un-asked-for.

## Why this shape

**A bot is an ordinary `Player` row**, not a special-cased actor. It has a
`display_name`, its games show up in `GET /api/v1/matches/`, and
`apps.achievements` never learns the difference — the one new thing about it
is a `Player.is_bot` flag and a sibling `BotProfile` row
(`apps.matches.models`) holding its accuracy and speed.
`apps.rankings` is the *one* exception to "looks like any other competitor",
and a deliberate one — see "Bots are never ranked" below.

### Bots are never ranked

`Matchup.is_ranked` is a plain boolean, decided once, at
`services.create_matchup`, from whether either side is a bot:
`is_ranked = not (player_one.is_bot or player_two.is_bot)`. Never re-derived
later — a `BotProfile` tuned mid-match, or a human's `is_bot` flag (there
isn't one to flip) cannot rewrite what kind of game this already was.

`apps.rankings.services.update_ratings_for_matchup` — the one hook that ever
touches a `Ranking` — is a no-op when `matchup.is_ranked` is `False`. That is
the whole mechanism: a bot game still plays out, still scores, still checks
achievements (`award_achievements_for_matchup` does not read `is_ranked` — a
"First Win" or "Perfect Match" earned against a bot is still a real result
for the human), but the exchange that would move a rating simply never runs.
One skip, not a one-sided credit to the human — crediting the human alone
would still be a rating built partly on games a human opponent never played.

Concretely, this is what "bots are pinned at 1000
(`DEFAULT_PLAYER_RATING`)" means: a bot is never handed a `Ranking` row at
all, because the only writer of one (`ratings.ensure_ranking`, called from
inside `update_ratings_for_matchup`) is never reached for an unranked
matchup. Belt and braces beyond that, in case a `Ranking` row for a bot ever
exists by some other path (a fixture, a manual admin edit):
`apps.rankings.selectors.ladder` filters `player__is_bot=False`, and
`unrated_players` (what `manage.py backfill_rankings` seeds) does too — a
bot never appears on a leaderboard and is never backfilled a rating to begin
with, whether or not the no-op above already made that moot.

`MatchupListSerializer`/`MatchupDetailSerializer` (`apps.matches.api
.serializers`) surface `is_ranked` on every row of `GET /api/v1/matches/` and
`/{id}/`, so a player can tell a practice game against a CPU opponent apart
from one that moved their ladder position without cross-referencing the
opponent's name.

**Nothing here teaches `apps.matches` a new way to decide correctness.** A
bot's answer is scored by the exact same `apps.questions.services.evaluate_answer`
a human's is — `apps.matches.bots.answering.build_bot_answer` only decides,
per question, whether to construct a payload that is deliberately right or
deliberately wrong, using the question's own answer key read directly from
the database (a bot has no serialized board to be shuffled at, and is not
the audience the anti-cheat shuffle in `apps.questions.api.serializers`
exists to defend against — see `backend/CLAUDE.md`'s section on that
serializer). A bot's response time is genuinely server-measured, the same
`constants.score_answer` machinery a human's is: the delay before a bot
calls `submit_answer` **is** its response time, not a number it reports.

### Speed is a percentage of the clock, not a fixed number of seconds

`BotProfile` stores `min_response_fraction`/`max_response_fraction` — a band
in `[0.0, 1.0]` — instead of a fixed millisecond band. This matters because
not every question gets the same amount of time: `apps.matches.constants
.time_limit_ms_for` already gives a matrix question 20 seconds against the
10-second fallback every other type gets
(`FALLBACK_QUESTION_TIME_LIMITS_MS`), and any future question type or authored
`time_limit_seconds` override can hand out a different number again. A fixed
"answers in 2–9 seconds" band only reads as fast-to-slow against *one*
specific clock; against a 20-second question, even the slowest bot (9s) would
still be answering with more than half the time left — recognisably faster
than intended, on that question only. A **percentage** of whatever the
question's own limit turns out to be keeps a bot's *relative* speed constant
across every question type, present or future — bot 1 always answers having
spent about 90% of the time it was given, bot 50 always about 20%, whether
that's 9s of a 10s question or 18s of a 20s one.

`apps.matches.bots.controller._next_state` is where this is realized: it
looks up the *current* question's own `time_limit_ms` (the same
`time_limit_ms_for` call `services.submit_answer` and the realtime watchdogs
use) and multiplies it by a fraction drawn uniformly from the bot's band, each
question, rather than ever reading a millisecond constant.

## The pieces

```
apps/matches/
  pool.py               + claim_for_bot()   — atomic withdraw for the fallback
  consumers.py           MatchmakingConsumer — spawns the 8s timer, and the
                          bot-play task once a bot is chosen
  models.py              + BotProfile        — accuracy + response-speed band
                          + Matchup.is_ranked — set once, in create_matchup
  bots/
    __init__.py           package docstring — the short version of this file
    selection.py           pick_bot_player_id() — draw one bot at random
    answering.py            build_bot_answer() — a right-or-wrong payload,
                             one builder per question type (SINGLE_ANSWER,
                             IMAGE_ANSWER, MULTIPLE_ANSWER, TRUE_FALSE,
                             FREE_TEXT, ORDERING, MATRIX)
    controller.py            run_bot() — the loop that plays a bot's side of
                              one live matchup through apps.matches.services
  management/commands/
    seed_bots.py            authors the 50-bot roster
```

### Matchmaking: the 8-second fallback

1. A player joins a category's pool (`MatchmakingConsumer.connect`). If
   nobody is already waiting, the player becomes the one waiting and the
   server sends `SEARCHING`.
2. With `FF_ENABLE_BOTS_IF_TIMEOUT` on, the consumer also spawns
   `_fall_back_to_bot_after_timeout`, which sleeps
   `MATCHMAKING_BOT_TIMEOUT_SECONDS` (8 by default) and then checks whether
   this player is *still* the one waiting.
3. If a human joined in the meantime, the player was already paired and this
   coroutine is a no-op (`pool.claim_for_bot` returns `False` — same
   `cache.add` mutex `pool.join_pool`/`leave_pool` already use, so the two
   codepaths cannot double-pair the same player).
4. Otherwise, `claim_for_bot` atomically withdraws the player from the pool,
   `apps.matches.bots.selection.pick_bot_player_id` draws a random bot, and
   `MatchmakingConsumer._pair_with_bot` creates and starts the matchup exactly
   the way a human-human pairing does — except there is no second socket to
   notify, so instead a `apps.matches.bots.controller.run_bot` task is
   spawned to play the bot's side.

If no bots have been seeded, the timeout fires into an empty roster; the
player is put back in the pool (`pool.join_pool`) rather than left stranded,
and a warning is logged.

### Playing: `run_bot`

A bot has no WebSocket of its own, so `run_bot` polls the matchup
(every 0.35s) instead of listening for `events.QUESTION_STARTED` on a
channel-layer group. Once a question is open, it:

1. Draws a target fraction of the *current question's own* time limit
   uniformly from the bot's `[min_response_fraction, max_response_fraction]`
   band, converts it to a millisecond target against that question's
   `time_limit_ms_for(...)`, and clamps it to land safely before the
   question's own deadline.
2. Sleeps the remaining delay.
3. Flips a weighted coin against `BotProfile.accuracy` to decide "correct" or
   "incorrect" for this question.
4. Builds a payload via `answering.build_bot_answer` and calls
   `apps.matches.services.submit_answer` — the identical call
   `apps.matches.consumers._submit_answer` makes for a real client's
   `ANSWER_SUBMIT` frame.
5. Reuses `consumers._close_question_if_ready` (the same one-broadcaster-wins
   `cache.add` mutex a human's own watchdog or the opponent's submission
   race against) to publish the result and advance the board.

A bot that would answer too late to land inside the time limit simply skips
that question and lets the human's own connect-time watchdog
(`consumers._watch_question_timeout`) close it on time-out, the same as a
human opponent going silent would.

`run_bot`'s task is tracked in a **module-level** set
(`apps.matches.bots.controller._bot_tasks`), not the per-consumer one
`consumers._WatchdogMixin` uses — see `backend/CLAUDE.md`'s note on
`asyncio.ensure_future` silently garbage-collecting an unheld task. A bot's
task must outlive the *human's* matchmaking consumer that spawned it, which
disconnects almost immediately (its one job — finding the game — is already
done), so tying the task's lifetime to that consumer's own `self` would be
wrong.

### The roster: `manage.py seed_bots`

```bash
uv run python manage.py seed_bots              # the default 50 bots
uv run python manage.py seed_bots --count 50
uv run python manage.py seed_bots --dry-run
```

Idempotent, upserting on display name (`CPU-01` … `CPU-50`) the same way
`sync_questions` upserts on slug — re-running it after tuning the curve below
corrects the existing 50 rows rather than inserting 50 more. Bots are never
deleted by this command: one may already be the recorded opponent in a played
matchup (`MatchupPlayer.player` is `PROTECT`, the same as a human's).

The roster is **leveled, not uniform** — bot 1 is the weakest, bot 50 the
strongest, every bot between them interpolated linearly on both axes
together:

| | Bot 1 (weakest) | Bot 50 (strongest) |
| --- | --- | --- |
| Accuracy | 30% | 90% |
| Response speed (band center, % of the question's own clock) | ~90% | ~20% |

Each bot's own response band is 12 percentage points wide, so it is
recognisably fast or slow rather than answering at the exact same instant
every question. On the 10-second fallback clock that is roughly "under 2s" to
"over 9s" — the brief's own numbers — but expressed as a **percentage of the
clock** rather than a fixed duration, so the same bot is still recognisably
fast or slow on a longer question (a 20-second matrix question, or any future
type/override) instead of merely looking faster because the clock got longer.
Nothing in `BotProfile` requires the two axes (accuracy, speed) to move
together for a *different* roster design; interpolating them together here is
just the simplest curve that spans both requested ranges end-to-end.

## What a bot does **not** get

- **No skill matching.** `pick_bot_player_id` draws uniformly at random —
  matchmaking's bot fallback exists to unblock someone with nobody else
  online, not to referee a fair fight. A future pass that wants difficulty
  matched to the waiting player's own rating can read `BotProfile.accuracy`
  the same way a leaderboard reads `Ranking`; nothing here forecloses it.
- **No special-cased scoring, rating, or achievement path.** A bot's matchup
  is scored, rated and evaluated for badges by the exact same
  `apps.matches.services.complete_matchup` / `apps.rankings.services
  .update_ratings_for_matchup` / `apps.achievements.services
  .award_achievements_for_matchup` calls a human-human matchup goes through.

## Testing

`apps/matches/tests/test_bots.py`:

- `BotAnswerRegistryTests` — every `QuestionType` has a bot answer builder
  (mirrors `apps.questions.tests.test_evaluation.RegistryCoverageTests`), and
  a "correct" choice always scores full credit while an "incorrect" one never
  does, across all seven question shapes.
- `SeedBotsCommandTests` — the command is idempotent and the roster spans the
  requested accuracy range end to end.
- `MatchmakingBotFallbackTests` — real sockets
  (`channels.testing.WebsocketCommunicator`, the same posture
  `test_realtime.py` takes), `@override_settings(FF_ENABLE_BOTS_IF_TIMEOUT=True,
  MATCHMAKING_BOT_TIMEOUT_SECONDS=0)`: a lone player is matched with a bot,
  and the bot plays its side of a full matchup to `MATCH_COMPLETED`.

`apps/matches/tests/test_services.py::CreateMatchupTests` — a two-human
matchup is `is_ranked`; a bot on either side is not.

`apps/rankings/tests/test_ratings.py`:

- `UnrankedMatchupTests` — completing or abandoning a bot matchup writes no
  `Ranking` row at all, for either side.
- `LadderSelectorTests.test_ladder_and_unrated_players_never_surface_a_bot` —
  even a bot with a `Ranking` row forced into existence directly never
  appears in `selectors.ladder` or `selectors.unrated_players`.
