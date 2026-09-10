# CPU (bot) opponents — architecture

## What this is

Matchmaking normally waits for a second human. This feature gives it a
fallback: if nobody else joins a category's pool within **15 seconds**, the
waiting player is paired against one of **50 seeded CPU players** instead of
waiting indefinitely.

- Each bot has a fixed **guessing probability between 30% and 90%** (how
  often it deliberately answers correctly).
- Each bot has a fixed **response-time band spanning under 2 seconds to over
  9 seconds** (how long it takes to submit each answer).
- The whole feature is behind one flag: **`FF_ENABLE_BOTS_IF_TIMEOUT`**. Off,
  none of this code path is ever reached — a lonely player simply keeps
  waiting, exactly like today.

| Setting | Env var | `config.settings.local` | Every other tier |
| --- | --- | --- | --- |
| Feature flag | `FF_ENABLE_BOTS_IF_TIMEOUT` | `True` (hardcoded) | `False` (default) |
| Timeout | `MATCHMAKING_BOT_TIMEOUT_SECONDS` | `15` (default) | `15` (default) |

`local.py` hardcodes the flag on regardless of the environment — a solo
developer running just this one process has nobody else to be matched
against, so leaving it off by default would make matchmaking hang forever in
the exact environment it needs to work zero-config in. Every other tier
(`test.py`, `production.py`) inherits `base.py`'s default of `False` and must
opt in explicitly via the environment, the same posture `LOGIN_LOCKOUT_ENFORCED`
and `MATCH_ABUSE_LIMITS_ENFORCED` already take for their own tier split. A
bot opponent moves ratings, awards achievements and appears in match history
exactly like a human one — nothing about it is a "test mode" default that
should leak into a real deployment un-asked-for.

## Why this shape

**A bot is an ordinary `Player` row**, not a special-cased actor. It has a
`display_name`, it takes a `Ranking`, its games show up in
`GET /api/v1/matches/`, and `apps.rankings`/`apps.achievements` never learn
the difference — the one new thing about it is a `Player.is_bot` flag and a
sibling `BotProfile` row (`apps.matches.models`) holding its accuracy and
speed. This mirrors how `apps.questions` keeps question types independent of
categories: the match/ranking/achievement engines must not need a special
case for "the other side of this race is a program," so the bot is made to
look, to every one of them, like any other competitor.

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

## The pieces

```
apps/matches/
  pool.py               + claim_for_bot()   — atomic withdraw for the fallback
  consumers.py           MatchmakingConsumer — spawns the 15s timer, and the
                          bot-play task once a bot is chosen
  models.py              + BotProfile        — accuracy + response-time band
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

### Matchmaking: the 15-second fallback

1. A player joins a category's pool (`MatchmakingConsumer.connect`). If
   nobody is already waiting, the player becomes the one waiting and the
   server sends `SEARCHING`.
2. With `FF_ENABLE_BOTS_IF_TIMEOUT` on, the consumer also spawns
   `_fall_back_to_bot_after_timeout`, which sleeps
   `MATCHMAKING_BOT_TIMEOUT_SECONDS` (15 by default) and then checks whether
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

1. Draws a target response time uniformly from the bot's own
   `[min_response_ms, max_response_ms]` band, clamped to land safely before
   the question's own deadline.
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
| Response time (band center) | ~9.5s | ~1.5s |

Each bot's own response band is 1.2s wide, so it is recognisably fast or slow
rather than answering at the exact same millisecond every question. This
spans the brief precisely — "guessing probability between 30% and 90%,
speed ability between less than 2 seconds and more than 9 seconds" — without
claiming those two axes have to move together for a *different* roster
design; nothing in `BotProfile` requires it.

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
