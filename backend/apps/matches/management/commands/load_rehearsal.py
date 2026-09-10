"""N simulated players, against a deployed instance's real HTTP + WebSocket
surface — a black-box rehearsal, not a call into ``apps.matches.services``.

    uv run --group dev python manage.py load_rehearsal \\
        --players 20 --category nba --base-url https://staging.knowdown.app

Each simulated player is a real account (``POST /auth/registration/``), a
real matchmaking socket, and a real matchup socket, answering at a randomised
"human" delay rather than the instant a service-layer test would. This is the
only way to rehearse what step 22-24 shipped: the actual gunicorn/uvicorn
processes, the actual Redis pool and channel layer, the actual database under
real concurrent load — a unit test proves the rules are right, this proves
the deployment can carry them.

**Every account this run creates is tagged in its email**:
``loadrehearsal-<run>-<n>@rehearsal.invalid`` — ``.invalid`` is the reserved
TLD (RFC 2606) for addresses that must never resolve, so nothing here can
misfire against a real inbox. ``manage.py load_rehearsal_teardown --run
<run>`` is the other half — see that command's docstring for exactly what it
does and does not remove, which is less than "every row this run touched":
``MatchupPlayer.player`` is ``PROTECT``, the same guard that keeps anyone's
match history from disappearing under them, and a rehearsal account is not
an exception to it.

Needs the ``dev`` dependency group (``httpx``, ``websockets`` — neither ships
in the runtime image) and a target that has ``PERMIT_PASSWORD_AUTH`` on,
since registration is how every simulated account signs in.
"""

from __future__ import annotations

import asyncio
import json
import random
import secrets
import statistics
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
import websockets
from django.core.management.base import BaseCommand, CommandError

from apps.matches import events
from shared.logging import get_logger

logger = get_logger(__name__)

#: The reserved-forever TLD (RFC 2606) — guarantees a rehearsal email can
#: never resolve to a real inbox, whatever the target's mail configuration.
EMAIL_DOMAIN = "rehearsal.invalid"

DEFAULT_WAIT_FOR_MATCH_SECONDS = 120
DEFAULT_MIN_ANSWER_DELAY_SECONDS = 1.0
DEFAULT_MAX_ANSWER_DELAY_SECONDS = 4.0


def _ws_base(http_base: str) -> str:
    """``https://host`` -> ``wss://host``; ``http://host`` -> ``ws://host``."""
    parsed = urlparse(http_base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}"


@dataclass
class PlayerRun:
    index: int
    email: str
    matched: bool = False
    wait_for_match_ms: int | None = None
    completed: bool = False
    match_duration_ms: int | None = None
    error: str | None = None


@dataclass
class RehearsalResult:
    run_id: str
    players: list[PlayerRun] = field(default_factory=list)

    def summary(self) -> str:
        matched = [p for p in self.players if p.matched]
        completed = [p for p in self.players if p.completed]
        errors = [p for p in self.players if p.error]
        lines = [
            f"run {self.run_id}: {len(self.players)} players, "
            f"{len(matched)} matched, {len(completed)} completed, {len(errors)} errored",
        ]
        waits = [p.wait_for_match_ms for p in matched if p.wait_for_match_ms is not None]
        if waits:
            lines.append(
                f"  wait for opponent (ms): min={min(waits)} "
                f"median={int(statistics.median(waits))} max={max(waits)}"
            )
        durations = [p.match_duration_ms for p in completed if p.match_duration_ms is not None]
        if durations:
            lines.append(
                f"  match duration (ms): min={min(durations)} "
                f"median={int(statistics.median(durations))} max={max(durations)}"
            )
        for p in errors:
            lines.append(f"  player {p.index} ({p.email}): {p.error}")
        return "\n".join(lines)


def _answer_payload(board: dict, rng: random.Random) -> dict:
    """A plausible, valid-shaped guess for whatever board the server sent —
    never a correct one on purpose. Scoring is not what this rehearses;
    ``services.evaluation`` already has that covered under
    ``apps.questions.tests.test_evaluation``. Every branch here mirrors one
    variant of ``apps.questions.schemas.answers.AnswerSubmission``.
    """
    question_type = board["type"]
    if question_type in ("single-answer", "image-answer"):
        option = rng.choice(board["options"])
        return {"type": question_type, "option_id": option["id"]}
    if question_type == "multiple-answer":
        options = board["options"]
        pick_count = rng.randint(1, len(options))
        chosen = rng.sample(options, pick_count)
        return {"type": question_type, "option_ids": [o["id"] for o in chosen]}
    if question_type == "true-false":
        return {"type": question_type, "answer": rng.choice([True, False])}
    if question_type == "free-text":
        return {"type": question_type, "text": f"rehearsal-guess-{rng.randint(0, 9999)}"}
    if question_type == "ordering":
        option_ids = [o["id"] for o in board["options"]]
        rng.shuffle(option_ids)
        return {"type": question_type, "option_ids": option_ids}
    if question_type == "matrix":
        cells = [
            {
                "row_id": cell["row_id"],
                "column_id": cell["column_id"],
                "answer": f"guess-{rng.randint(0, 999)}",
            }
            for cell in board["cells"]
        ]
        return {"type": question_type, "cells": cells}
    raise ValueError(f"Unknown question type from the server: {question_type!r}")


async def _register(client: httpx.AsyncClient, *, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/registration/",
        json={"email": email, "password1": password, "password2": password},
    )
    response.raise_for_status()
    return response.json()["access"]


async def _play_matchup(
    *, ws_base: str, token: str, matchup_id: str, rng: random.Random,
    min_delay: float, max_delay: float,
) -> None:
    url = f"{ws_base}/ws/v1/matches/{matchup_id}/?token={token}"
    async with websockets.connect(url) as socket:
        while True:
            raw = await asyncio.wait_for(socket.recv(), timeout=60)
            message = json.loads(raw)
            message_type = message.get("type")
            if message_type == events.QUESTION_STARTED:
                board = message["question"]
                time_limit_s = message["time_limit_ms"] / 1000
                # "At human speed": a randomised delay, capped well under the
                # server's own clock so a slow rehearsal run still submits
                # before the question times out on its own.
                delay = min(rng.uniform(min_delay, max_delay), time_limit_s * 0.8)
                await asyncio.sleep(delay)
                await socket.send(
                    json.dumps(
                        {
                            "type": events.ANSWER_SUBMIT,
                            "order": message["order"],
                            "payload": _answer_payload(board, rng),
                        }
                    )
                )
            elif message_type == events.MATCH_COMPLETED:
                return
            # QUESTION_RESULT, PLAYER_ANSWERED, OPPONENT_DISCONNECTED,
            # OPPONENT_RECONNECTED, ERROR: informational, nothing to send back.


async def _run_player(
    *, run: PlayerRun, base_url: str, ws_base: str, category: str, password: str,
    wait_for_match_seconds: int, min_delay: float, max_delay: float,
) -> None:
    rng = random.Random(f"{run.email}:{time.time_ns()}")
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
            token = await _register(client, email=run.email, password=password)

        queued_at = time.monotonic()
        mm_url = f"{ws_base}/ws/v1/matchmaking/{category}/?token={token}"
        matchup_id: str | None = None
        async with websockets.connect(mm_url) as socket:
            while matchup_id is None:
                raw = await asyncio.wait_for(socket.recv(), timeout=wait_for_match_seconds)
                message = json.loads(raw)
                if message.get("type") == events.MATCH_FOUND:
                    matchup_id = message["matchup_id"]

        run.matched = True
        run.wait_for_match_ms = int((time.monotonic() - queued_at) * 1000)

        match_started = time.monotonic()
        await _play_matchup(
            ws_base=ws_base, token=token, matchup_id=matchup_id, rng=rng,
            min_delay=min_delay, max_delay=max_delay,
        )
        run.completed = True
        run.match_duration_ms = int((time.monotonic() - match_started) * 1000)
    except Exception as exc:  # noqa: BLE001 — one player's failure must not sink the run
        run.error = f"{type(exc).__name__}: {exc}"


async def _rehearse(
    *, run_id: str, player_count: int, base_url: str, category: str,
    wait_for_match_seconds: int, min_delay: float, max_delay: float,
) -> RehearsalResult:
    ws_base = _ws_base(base_url)
    password = secrets.token_urlsafe(16)
    result = RehearsalResult(run_id=run_id)
    runs = [
        PlayerRun(index=i, email=f"loadrehearsal-{run_id}-{i}@{EMAIL_DOMAIN}")
        for i in range(player_count)
    ]
    result.players = runs
    await asyncio.gather(
        *(
            _run_player(
                run=run, base_url=base_url, ws_base=ws_base, category=category,
                password=password, wait_for_match_seconds=wait_for_match_seconds,
                min_delay=min_delay, max_delay=max_delay,
            )
            for run in runs
        )
    )
    return result


class Command(BaseCommand):
    help = (
        "Rehearse N simulated players against a deployed instance's real "
        "HTTP + WebSocket surface, answering at human speed."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--players", type=int, required=True, help="How many simulated players.")
        parser.add_argument("--category", required=True, help="Category slug to queue for, e.g. nba.")
        parser.add_argument(
            "--base-url", required=True,
            help="The deployed instance's HTTP origin, e.g. https://staging.knowdown.app",
        )
        parser.add_argument(
            "--run", default=None,
            help="Run id tagging every account this rehearsal creates (default: random). "
            "Pass this to `load_rehearsal_teardown --run` afterwards.",
        )
        parser.add_argument(
            "--wait-for-match-seconds", type=int, default=DEFAULT_WAIT_FOR_MATCH_SECONDS,
        )
        parser.add_argument(
            "--min-answer-delay", type=float, default=DEFAULT_MIN_ANSWER_DELAY_SECONDS,
        )
        parser.add_argument(
            "--max-answer-delay", type=float, default=DEFAULT_MAX_ANSWER_DELAY_SECONDS,
        )

    def handle(self, *args, **options) -> None:
        if options["players"] < 2:
            raise CommandError("--players needs at least 2 — matchmaking pairs two at a time.")
        run_id = options["run"] or uuid.uuid4().hex[:8]
        self.stdout.write(f"Starting rehearsal run {run_id!r} with {options['players']} players…")

        result = asyncio.run(
            _rehearse(
                run_id=run_id,
                player_count=options["players"],
                base_url=options["base_url"].rstrip("/"),
                category=options["category"],
                wait_for_match_seconds=options["wait_for_match_seconds"],
                min_delay=options["min_answer_delay"],
                max_delay=options["max_answer_delay"],
            )
        )

        self.stdout.write(result.summary())
        logger.info(
            "Load rehearsal finished",
            summary=result.summary().splitlines()[0],
            count=len(result.players),
        )
        self.stdout.write(
            self.style.WARNING(
                f"\nTear down this run's accounts with: "
                f"manage.py load_rehearsal_teardown --run {run_id}"
            )
        )
