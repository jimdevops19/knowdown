"""Phase two: the whole cast, playing at once, on one clock.

Eighty players is forty matchups — that is the arithmetic the whole test is
built on (``apps.matches.constants.PLAYERS_PER_MATCHUP``), and it is why the
player count is the one knob worth an environment variable. Every player is a
coroutine holding two real sockets in turn; they spend nearly all of their
time waiting on the network, so one event loop carries hundreds of them and a
thread per player would buy nothing.

A **round** is the whole cast queueing, pairing off, and playing to the final
whistle. ``--rounds`` repeats it against a deployment that is no longer cold —
caches warm, connection pools full, and a question catalog the earlier round
has already drawn from.

Nothing here decides what a person does; that is ``play.py``'s job. This
module decides who plays, when everybody starts, and — the part worth
reading — **what counts as a problem** once they have all finished.
"""

from __future__ import annotations

import asyncio
import ssl
import statistics
import sys
from dataclasses import dataclass, field

from .client import Api
from .config import Config
from .metrics import Metrics
from .play import PlayResult, play_one_match
from .state import RunState, SeededPlayer


@dataclass
class RunReport:
    """Every round's results, and the verdict drawn from them."""

    rounds: list[list[PlayResult]] = field(default_factory=list)

    @property
    def results(self) -> list[PlayResult]:
        return [result for round_results in self.rounds for result in round_results]

    def findings(self, *, config: Config) -> list[str]:
        """What went wrong, in the order it matters.

        Empty is the only good answer. Each line is phrased as the thing an
        operator would go and look at, not as a counter — "3 matches were
        abandoned" sends somebody to the realtime pod's logs; "abandoned=3"
        sends them back here to ask what that means.
        """
        results = self.results
        expected_per_round = (len(results) // max(len(self.rounds), 1))
        findings: list[str] = []

        unmatched = [r for r in results if not r.matched]
        if unmatched:
            findings.append(
                f"{len(unmatched)}/{len(results)} players were never paired — the room's "
                "pool did not put anybody opposite them. Look at the realtime pod: a "
                "`1013 pool busy` close means `apps.matches.pool`'s mutex is the "
                "bottleneck, a silent wait means the cache the pool lives in is not "
                "shared across replicas."
            )

        stranded = [r for r in results if r.matched and not r.completed]
        if stranded:
            findings.append(
                f"{len(stranded)} players were paired but their match never finished. "
                "A match that stops mid-question is the watchdog "
                "(`consumers._watch_question_timeout`) not firing, or the channel "
                "layer dropping the broadcast that would have closed it."
            )

        abandoned = [r for r in results if r.outcome == "abandoned"]
        if abandoned:
            findings.append(
                f"{len(abandoned)} matches ended as `abandoned` rather than `played`. "
                "Every socket here was held open to the final whistle, so the server "
                "decided a connected player had left: `RECONNECT_GRACE_SECONDS` "
                "elapsing under load, or presence/heartbeat falling behind."
            )

        rate_limited = [r for r in results if "rate_limited" in r.errors]
        if rate_limited:
            findings.append(
                f"{len(rate_limited)} players were rate-limited mid-match "
                "(`apps.matches.abuse`). At one answer per question this should not "
                "happen; check ANSWER_SUBMIT_RATE_LIMIT against the number of rounds."
            )

        failures = [r for r in results if r.failure]
        if failures:
            kinds: dict[str, int] = {}
            for result in failures:
                kinds[result.failure.split(":")[0]] = kinds.get(result.failure.split(":")[0], 0) + 1
            findings.append(
                f"{len(failures)} players failed outright: "
                + ", ".join(f"{k} ×{v}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]))
            )

        waits = [r.wait_for_match_ms for r in results if r.wait_for_match_ms is not None]
        if waits and max(waits) > 30_000:
            findings.append(
                f"the slowest pairing took {max(waits) / 1000:.0f}s. With "
                f"{expected_per_round} players joining at once, nobody should wait "
                "more than a few seconds for an opponent."
            )
        return findings

    def summary(self, *, config: Config) -> str:
        results = self.results
        matched = [r for r in results if r.matched]
        completed = [r for r in results if r.completed]
        played = [r for r in completed if r.outcome == "played"]
        lines = [
            f"{len(self.rounds)} round(s) · {len(results)} player-matches · "
            f"{len(matched)} paired · {len(completed)} finished "
            f"({len(played)} played out, {len(completed) - len(played)} abandoned)",
            f"  questions answered: {sum(r.questions_answered for r in results)}"
            f"   hints delivered: {sum(r.hints_received for r in results)}",
        ]
        lines += [
            _distribution("wait for opponent", [r.wait_for_match_ms for r in matched]),
            _distribution("match duration", [r.match_duration_ms for r in completed]),
        ]
        return "\n".join(line for line in lines if line)


async def run(*, config: Config, state: RunState, metrics: Metrics) -> RunReport:
    players = state.players
    if len(players) % 2:
        # The pool pairs two at a time; an odd cast leaves one person in a
        # queue nobody joins, and reporting that as "never paired" would be
        # this driver blaming the platform for its own arithmetic.
        print(f"  note: {len(players)} seeded players — one sits out each round")
        players = players[:-1]

    print(
        f"running {config.rounds} round(s): {len(players)} players → "
        f"{len(players) // 2} simultaneous matchups in room {state.room!r}"
    )
    print(f"  watch: {config.base_url}\n")

    ssl_context = _ssl_context(config)
    apis = {
        player.email: _api(player, config=config, metrics=metrics) for player in players
    }
    report = RunReport()
    try:
        for round_number in range(1, config.rounds + 1):
            if config.rounds > 1:
                print(f"— round {round_number}/{config.rounds}")
            results = await asyncio.gather(
                *(
                    play_one_match(
                        api=apis[player.email],
                        player=player,
                        room=state.room,
                        base_url=config.base_url,
                        metrics=metrics,
                        answer_delay=config.answer_delay,
                        wait_for_match_seconds=config.wait_for_match_seconds,
                        join_delay=index * config.join_stagger_seconds,
                        ssl_context=ssl_context,
                    )
                    for index, player in enumerate(players)
                )
            )
            report.rounds.append(list(results))
            print("  " + report.summary(config=config).splitlines()[0])
    finally:
        # Closing every pool is not tidiness: eighty leaked connection pools
        # is eighty sets of sockets the ingress is still holding when the
        # next phase (teardown) tries to talk to it.
        await asyncio.gather(*(api.aclose() for api in apis.values()))

    return report


def print_report(report: RunReport, metrics: Metrics, *, config: Config) -> int:
    """The console's last word, and the process's exit status.

    Non-zero when something went wrong, so ``task stress:all`` is a thing CI
    could run: a load test that always exits 0 is a load test nobody reads.
    """
    print("\n" + report.summary(config=config))
    print("\n" + metrics.format_table(title="run complete"))

    findings = report.findings(config=config)
    if not findings:
        print("\nno problems found: every player was paired and every match finished.")
        return 0
    print("\nproblems found:", file=sys.stderr)
    for finding in findings:
        print(f"  · {finding}", file=sys.stderr)
    return 1


def _api(player: SeededPlayer, *, config: Config, metrics: Metrics) -> Api:
    api = Api(
        base_url=config.base_url,
        metrics=metrics,
        verify=config.verify_tls,
        timeout=config.timeout,
    )
    api.adopt(
        email=player.email,
        password=player.password,
        access=player.access,
        refresh=player.refresh or None,
    )
    return api


def _ssl_context(config: Config):
    """What ``websockets.connect`` should do about the certificate.

    ``None`` for a plain ``ws://`` target — passing a context there is an
    error, not a no-op. Otherwise staging's private step-ca means verification
    is off by default, the same trade the HTTP client makes.
    """
    if not config.base_url.startswith("https"):
        return None
    if config.verify_tls:
        return ssl.create_default_context()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _distribution(label: str, values: list[int | None]) -> str:
    samples = sorted(v for v in values if v is not None)
    if not samples:
        return ""
    return (
        f"  {label} (ms): min={samples[0]} "
        f"median={int(statistics.median(samples))} max={samples[-1]}"
    )
