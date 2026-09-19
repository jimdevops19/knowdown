# stress

A load test against a **deployed** knowdown — staging, not this laptop. It
registers a cast of real-named people, puts **all of them in the same lobby
room at the same moment**, and lets the matchmaking pool do what it does:
80 players become 40 matchups, played out over real sockets, at once.

It exists to be watched. The console numbers here are the client's side of the
story; the server's side is the journey log `backend/CLAUDE.md` describes —
`action="queued"`, `"matched"`, `"answered"`, `"completed"`.

Everything it creates is tagged, and `stress teardown` removes all of it.

```
stress/
  config.yml     the shape of a run — how many players, how many rounds, how fast
  src/           the engine: client, roster, seeding, the play loop, teardown
  .state/        one run's accounts and tokens (git-ignored, throwaway)
```

## Running one

```bash
task stress:seed        # register the cast (slow — see "Signing up is throttled")
task stress:run         # everybody queues at once; this is the measurement
task stress:teardown    # deletes every row the run created, and says so
```

`task stress:all` does all three back to back, with the teardown deferred so it
still runs if the load phase fails or you interrupt it.

**The player count is the knob.** Two players per matchup, so the default 80 is
40 games running side by side.

```bash
task stress:all                 # 80 players → 40 simultaneous matchups
task stress:all PLAYERS=150     # 150 players → 75 matchups
task stress:all PLAYERS=36      # a smaller rehearsal → 18 matchups
```

`PLAYERS` is read as `KNOWDOWN_STRESS_PLAYERS`, so `PLAYERS=150 task
stress:all` works too. `ROUNDS=3` plays the whole cast three times over,
against a deployment that is no longer cold.

The target defaults to `https://knowdown.<this Mac's LAN IP>.nip.io`, which is
the hostname the staging ingress actually answers on. Override it for anything
else:

```bash
task stress:seed BASE_URL=http://localhost:8000
```

Arguments pass through after `--`:

```bash
task stress:run -- --rounds 3 --join-stagger 0
task stress:seed -- --room nba-room-finals
task stress:status
task stress:teardown -- --dry-run     # count the tagged rows, delete nothing
```

Without go-task, the same thing directly:

```bash
KNOWDOWN_STRESS_BASE_URL=https://knowdown.10.100.102.7.nip.io \
  uv run --group dev python -m stress.src.cli seed --players 36
```

## The three phases, and why they are three

**Seed** registers the cast through the public API — ordinary HTTP calls a real
client could make, no ORM and no fixtures — so the rows it leaves are exactly
the shape the app itself produces. Each account signs up
(`POST /auth/registration/`) and then claims its name
(`PATCH /players/me/`), which is the same two-step the SPA's welcome screen
walks.

**Run** is the measurement. Every player joins the room's matchmaking socket
within a few seconds of every other, waits to be paired, moves to their matchup
socket, and answers each question after a randomised human delay until the final
whistle. Nothing calls `apps.matches.services`; every step is a real frame on a
real socket against the deployed `realtime` process, which is the only way to
exercise uvicorn, the Redis channel layer, the shared pool mutex and Postgres
under genuine concurrency.

It ends with a verdict rather than a wall of numbers — **and a non-zero exit
status when it finds something**, so the whole cycle is a thing CI could be
asked to pass:

| finding | what it means |
|---|---|
| players never paired | the pool did not put anybody opposite them. A `1013 pool busy` close is `apps.matches.pool`'s mutex as the bottleneck; a silent wait is the pool's cache not being shared across replicas |
| paired, never finished | a match stopped mid-question: the watchdog not firing, or the channel layer dropping the broadcast that closes it |
| matches `abandoned` | the server decided a *connected* player had left. Every socket here is held to the whistle, so this is `RECONNECT_GRACE_SECONDS` elapsing under load |
| rate-limited mid-match | `apps.matches.abuse` refusing answers. At one per question it should never fire |

**Teardown** runs `manage.py purge_stress` *inside* the deployment
(`kubectl exec` into the backend pod), because deleting an account is not
something the API offers and should not be. It finds rows by their **tags**,
not by the state file — so it can clean up after a run whose state file was
lost, or after two runs at once — then re-counts and tells you whether anything
is left.

Pass `--local` to purge a backend running in this checkout instead of the
cluster.

## What is tagged, and how it goes away

| | |
|---|---|
| accounts | email at `@stress.knowdown.test` (RFC 2606's reserved-forever TLD, so nothing here can reach a real inbox) |
| competitors | `Player.display_name` starts with `Stress` — the second handle, and the one that still works after `Player.user` has been `SET_NULL`'d |

`purge_stress` walks those tags leaf-first through answers, questions, matchup
sides, matchups, rankings and badges, then the competitors and finally the
logins — **hard** deletes, not the platform's usual soft delete, because a
soft-deleted `Player` still holds its name in the unique index.

> The driver's copy of the tags lives in [`src/tags.py`](src/tags.py) and the
> backend's in `apps/matches/management/commands/purge_stress.py`. They are two
> halves of one contract across an HTTP boundary no import can cross — change
> one, change the other.

**A matchup with a real person on the other side is left alone**, and so is the
stress competitor inside it. That pairing is not supposed to happen — a stress
run should have staging to itself — but the pool is global, and anybody tapping
"play" during a run joins the same queue. Half a match is not a thing to delete:
it would edit a real person's history, which is the objection
`MatchupPlayer.player`'s own `PROTECT` exists to raise. What is left behind is
inert and named `Stress …`, and the command says how much of it there is rather
than reporting a clean sweep it did not make.

**`purge_stress` has to exist in the deployed image.** After pulling a change to
it, `task publish:local:backend && task rollout:staging:backend` before relying
on the teardown.

## Signing up is throttled, and that is the platform working

`RegisterView` shares the `login` throttle scope — **10/min per IP** by default
(`THROTTLE_LOGIN`) — and every account this seeds comes from one machine. The
client waits out a 429 on the server's own `Retry-After` rather than failing it,
so seeding is *slow*, not broken: 36 accounts took **191 seconds** against
unmodified staging, and 80 takes around eight minutes.

That is why seeding is a separate command from running. The state file keeps the
cast, so you can apply load again and again without paying for it twice.

To make it seconds instead, raise the ceiling on the target for the duration of
the exercise — in `rpool_ops/fluxcd/apps/knowdown-staging/kustomization.yaml`,
on the `backend` Deployment:

```yaml
- op: add
  path: /spec/template/spec/containers/0/env/-
  value:
    name: THROTTLE_LOGIN
    value: "600/min"
```

Staging only, and worth putting back: the ceiling is what stops one client
working through a word list all day.

## Reading the output

```
1 round(s) · 36 player-matches · 36 paired · 36 finished (36 played out, 0 abandoned)
  questions answered: 192   hints delivered: 36
  wait for opponent (ms): min=486 median=1907 max=2065
  match duration (ms): min=9185 median=19478 max=26174

run complete  ·      29s  ·     264 calls  ·    9.1 req/s  ·  0 failed  ·  0 expected
  call                            n   fail      p50      p95      max
  answer acknowledged           192      0      58m     506m     869m
  join matchup                   36      0     709m     881m     881m
  wait for opponent              36      0    1896m    2051m    2066m
```

`p50`/`p95`/`max` are milliseconds, measured **client-side** — queueing at the
ingress included, which is the number a player would feel and one the server's
own metrics cannot see.

- **wait for opponent** — socket open to `match.found`. With the whole cast
  joining at once this should be seconds; the floor is the join stagger.
- **join matchup** — the matchup socket's handshake, which includes the server
  dealing the first question.
- **answer acknowledged** — `answer.submit` sent to this player's own
  `player.answered` echo coming back. The closest thing here to "how long did
  the write take", and the number that moves first when the database is the
  bottleneck.
- **failed** means something went wrong: a 5xx, a timeout, a refused
  connection, a socket closed mid-match. **expected** is counted apart —
  a 429 while seeding is the throttle doing its job, and folding those in would
  leave the headline number meaning nothing.

## Notes

- **Every socket sends an `Origin` header.** `config/asgi.py` wraps the routes
  in `AllowedHostsOriginValidator`, and channels rejects a *missing* Origin at
  the handshake, not only a wrong one. A driver that omitted it sees every
  connection refused before it reaches a consumer, with nothing in the log but
  `REJECT` — which is the first thing to check if a run reports
  `handshake 403`.
- **`answers.py` covers all nine question types**, including `gradual-hints`
  and `name-as-many`. A type with no branch sinks one player's whole match and
  reads on the console as a platform failure it isn't.
- **Bot fallback is off by default** (`FF_ENABLE_BOTS_IF_TIMEOUT`). With it on,
  a player left waiting past `MATCHMAKING_BOT_TIMEOUT_SECONDS` is paired with a
  CPU opponent instead, and the run silently measures fewer human matchups than
  it asked for.
- **The run refuses to target anything that isn't recognisably staging or
  local.** There is no production tier yet; when there is,
  `src/config.py::_refuse_production` is the guard that has to learn about it.
- **TLS verification is off by default.** Staging's certificate comes from a
  private step-ca; pass `--verify-tls` if you have the CA trusted.
- **`.state/run.json` holds throwaway passwords and JWTs** for the seeded
  accounts. It is git-ignored, and the teardown deletes it. Losing it is
  survivable — the purge works from tags.
- **An odd `PLAYERS` is rounded down.** A matchup is a race between exactly two
  people, and the alternative is one player left in a queue nobody joins, which
  reads in the results as a platform failure it isn't.
- **Two runs at once** are fine: emails and display names carry a per-run id.
  But teardown is by tag, so it removes *both*.
