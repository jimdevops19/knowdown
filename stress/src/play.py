"""One simulated person's journey, over the two sockets a real client uses.

    queue in a room  →  get paired  →  play the match out  →  final whistle

Nothing here reaches into ``apps.matches.services``. Every step is a frame on
a real WebSocket against the deployed ``realtime`` process, answered at a
randomised human delay, because the whole reason this exists is to exercise
what a unit test cannot: uvicorn, the Redis channel layer, the shared pool
mutex, and the database underneath eighty of these at once.

The protocol is ``apps.matches.events``; the routes are
``apps.matches.routing``. Both are a published contract, which is what makes
it safe for a driver outside the Django process to speak them.

**What this records, and why those things.** The server's own journey log
already counts queued/matched/answered/completed. What it cannot see is the
*client's* experience of the same events, which is what the numbers here are:
how long a player stared at "Searching…", how long the server took to
acknowledge an answer, and — the one that matters most — whether the match
reached a real finish or was handed to somebody by
``services.abandon_matchup`` because this client's socket fell over.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import websockets

from .answers import build_answer
from .metrics import Metrics

# Close codes from ``apps.matches.consumers``. Two halves of one contract
# across a socket no import can cross — same rule as ``tags.py``.
CLOSE_MATCHED = 4200
CLOSE_UNAUTHENTICATED = 4401
CLOSE_NOT_FOUND = 4404
CLOSE_RATE_LIMITED = 4429

# ``apps.matches.events`` — likewise.
SEARCHING = "searching"
MATCH_FOUND = "match.found"
QUESTION_STARTED = "question.started"
HINT_REVEALED = "hint.revealed"
PLAYER_ANSWERED = "player.answered"
QUESTION_RESULT = "question.result"
MATCH_COMPLETED = "match.completed"
OPPONENT_DISCONNECTED = "opponent.disconnected"
ERROR = "error"
ANSWER_SUBMIT = "answer.submit"

#: How long one frame may take to arrive during a live match before the
#: client gives up on it. Comfortably past the longest question clock in the
#: catalog (30s for ``name-as-many``) plus the read delay and an opponent
#: taking every second of it.
FRAME_TIMEOUT_SECONDS = 90


@dataclass
class PlayResult:
    """What became of one player in one round. The unit the run reports on."""

    display_name: str
    matched: bool = False
    completed: bool = False
    #: ``played`` or ``abandoned`` — straight off ``match.completed``. An
    #: abandoned match under load is the headline finding, not a detail: it
    #: means a socket this driver was holding open was declared gone.
    outcome: str | None = None
    won: bool | None = None
    score: int | None = None
    wait_for_match_ms: int | None = None
    match_duration_ms: int | None = None
    questions_answered: int = 0
    hints_received: int = 0
    #: Server-sent ``error`` frames — a refused submission, a rate limit.
    #: Counted rather than raised: they are the game answering, not the
    #: transport failing.
    errors: list[str] = field(default_factory=list)
    failure: str | None = None


def ws_base(http_base: str) -> str:
    """``https://host`` → ``wss://host``; ``http://host`` → ``ws://host``."""
    parsed = urlparse(http_base)
    return f"{'wss' if parsed.scheme == 'https' else 'ws'}://{parsed.netloc}"


def origin_for(http_base: str) -> str:
    """The ``Origin`` header every socket here has to send.

    ``config/asgi.py`` wraps the routes in channels'
    ``AllowedHostsOriginValidator``, and channels rejects a **missing**
    ``Origin`` at the handshake, not only a wrong one — a browser always sends
    it, so the validator has no reason to treat absence as permission. The
    ``websockets`` client sends none unless told to, which is why this exists
    and why a driver that omitted it would see every connection refused
    before it reached a consumer, with nothing in the log but ``REJECT``.

    The target's own origin is the right value: it is what the SPA served
    from that host sends, and it is in the deployment's
    ``CORS_ALLOWED_ORIGINS``/``ALLOWED_HOSTS`` by construction.
    """
    parsed = urlparse(http_base)
    return f"{parsed.scheme}://{parsed.netloc}"


async def play_one_match(
    *,
    api,
    player,
    room: str,
    base_url: str,
    metrics: Metrics,
    answer_delay: tuple[float, float],
    wait_for_match_seconds: int,
    join_delay: float,
    ssl_context,
) -> PlayResult:
    """Queue, get paired, play it out. One round for one person."""
    result = PlayResult(display_name=player.display_name)
    rng = random.Random(f"{player.email}:{time.time_ns()}")
    socket_base = ws_base(base_url)
    origin = origin_for(base_url)

    # The cast arriving inside one millisecond is a thundering herd against a
    # single `cache.add` mutex and is not what a busy lobby looks like.
    if join_delay:
        await asyncio.sleep(join_delay)

    try:
        token = await _usable_token(api)
        matchup_id = await _find_match(
            socket_base=socket_base,
            room=room,
            token=token,
            metrics=metrics,
            result=result,
            wait_for_match_seconds=wait_for_match_seconds,
            ssl_context=ssl_context,
            origin=origin,
        )
        if matchup_id is None:
            return result

        await _play(
            socket_base=socket_base,
            matchup_id=matchup_id,
            token=token,
            player=player,
            metrics=metrics,
            result=result,
            rng=rng,
            answer_delay=answer_delay,
            ssl_context=ssl_context,
            origin=origin,
        )
    except Exception as exc:  # noqa: BLE001 — one player's failure must not sink the run
        result.failure = f"{type(exc).__name__}: {exc}"
    return result


async def _usable_token(api) -> str:
    """The access token to put on the socket's query string.

    A WebSocket cannot set an ``Authorization`` header from a browser, which
    is why ``?token=`` exists at all (``apps.matches.authentication``) — and
    why an expired one closes the socket with 4401 rather than answering 401
    in a way the client could retry. So it is checked here, before the socket,
    where a refresh is a cheap HTTP call.
    """
    if not api.access:
        await api.reauthenticate()
    return api.access or ""


async def _find_match(
    *,
    socket_base: str,
    room: str,
    token: str,
    metrics: Metrics,
    result: PlayResult,
    wait_for_match_seconds: int,
    ssl_context,
    origin: str,
) -> str | None:
    """Sit in the room's pool until somebody is put opposite.

    The server closes this socket itself once it has said ``match.found``
    (``CLOSE_MATCHED``); the ``async with`` is what makes sure it is closed
    from this end too, because an abandoned matchmaking socket still counts
    against ``MAX_CONCURRENT_SOCKETS_PER_PLAYER``.
    """
    url = f"{socket_base}/ws/v1/matchmaking/room/{room}/?token={token}"
    queued_at = time.monotonic()
    try:
        async with websockets.connect(
            url, ssl=ssl_context, origin=origin, open_timeout=30
        ) as socket:
            while True:
                raw = await asyncio.wait_for(socket.recv(), timeout=wait_for_match_seconds)
                message = json.loads(raw)
                if message.get("type") == MATCH_FOUND:
                    waited = time.monotonic() - queued_at
                    result.matched = True
                    result.wait_for_match_ms = int(waited * 1000)
                    metrics.record(
                        label="wait for opponent", seconds=waited, ok=True, status="200"
                    )
                    return message["matchup_id"]
                if message.get("type") == ERROR:
                    result.errors.append(str(message.get("code", "error")))
                # `searching` is the server's cue that the spinner is real.
                # Nothing to do with it but keep waiting.
    except asyncio.TimeoutError:
        metrics.record(
            label="wait for opponent",
            seconds=time.monotonic() - queued_at,
            ok=False,
            status="no opponent",
        )
        result.failure = f"no opponent within {wait_for_match_seconds}s"
        return None
    except websockets.exceptions.WebSocketException as exc:
        metrics.record(
            label="wait for opponent",
            seconds=time.monotonic() - queued_at,
            ok=False,
            status=_socket_status(exc),
        )
        result.failure = f"matchmaking socket: {_socket_status(exc)}"
        return None


async def _play(
    *,
    socket_base: str,
    matchup_id: str,
    token: str,
    player,
    metrics: Metrics,
    result: PlayResult,
    rng: random.Random,
    answer_delay: tuple[float, float],
    ssl_context,
    origin: str,
) -> None:
    """The live game: answer what is asked until the final whistle."""
    url = f"{socket_base}/ws/v1/matches/{matchup_id}/?token={token}"
    started = time.monotonic()
    #: When this client sent its answer to question N, so the server's
    #: acknowledgement of it can be timed. Keyed by order: a question can be
    #: answered once (``services.submit_answer`` is idempotent), but the
    #: frames for two questions can overlap around a close.
    sent_at: dict[int, float] = {}

    try:
        async with websockets.connect(
            url, ssl=ssl_context, origin=origin, open_timeout=30
        ) as socket:
            metrics.record(
                label="join matchup", seconds=time.monotonic() - started, ok=True, status="200"
            )
            while True:
                raw = await asyncio.wait_for(socket.recv(), timeout=FRAME_TIMEOUT_SECONDS)
                message = json.loads(raw)
                kind = message.get("type")

                if kind == QUESTION_STARTED:
                    await _answer(
                        socket=socket,
                        message=message,
                        rng=rng,
                        answer_delay=answer_delay,
                        sent_at=sent_at,
                        result=result,
                    )
                elif kind == PLAYER_ANSWERED:
                    # Only *this* player's own echo is a measurement; the
                    # opponent's says nothing about our own round trip.
                    if str(message.get("player_id")) == player.player_id:
                        order = message.get("order")
                        if order in sent_at:
                            metrics.record(
                                label="answer acknowledged",
                                seconds=time.monotonic() - sent_at.pop(order),
                                ok=True,
                                status="200",
                            )
                elif kind == HINT_REVEALED:
                    result.hints_received += 1
                elif kind == MATCH_COMPLETED:
                    result.completed = True
                    result.outcome = message.get("outcome")
                    result.match_duration_ms = int((time.monotonic() - started) * 1000)
                    scores = message.get("scores") or {}
                    result.score = scores.get(player.player_id)
                    winner = message.get("winner_player_id")
                    result.won = None if winner is None else winner == player.player_id
                    return
                elif kind == ERROR:
                    result.errors.append(str(message.get("code", "error")))
                elif kind == OPPONENT_DISCONNECTED:
                    # Informational. The match is not over — `abandon_matchup`
                    # decides that after the grace window, and it arrives as an
                    # ordinary `match.completed`.
                    result.errors.append("opponent.disconnected")
                # QUESTION_RESULT: the answer key, for a screen nobody is
                # watching here.
    except asyncio.TimeoutError:
        metrics.record(
            label="join matchup",
            seconds=time.monotonic() - started,
            ok=False,
            status="frame timeout",
        )
        result.failure = f"no frame for {FRAME_TIMEOUT_SECONDS}s mid-match"
    except websockets.exceptions.WebSocketException as exc:
        metrics.record(
            label="join matchup",
            seconds=time.monotonic() - started,
            ok=False,
            status=_socket_status(exc),
        )
        result.failure = f"matchup socket: {_socket_status(exc)}"


async def _answer(
    *,
    socket,
    message: dict,
    rng: random.Random,
    answer_delay: tuple[float, float],
    sent_at: dict[int, float],
    result: PlayResult,
) -> None:
    """Think for a moment, then send one answer.

    The delay is capped well inside the server's own clock: a driver that
    occasionally timed out would be measuring its own slowness as the
    platform's. ``QUESTION_READ_DELAY_SECONDS`` means the clock has not even
    started for the first few seconds, so this is conservative twice over.
    """
    order = message["order"]
    if order in sent_at:
        return  # already answered; a reconnect's replay of the same question
    time_limit_s = message.get("time_limit_ms", 10_000) / 1000
    delay = min(rng.uniform(*answer_delay), time_limit_s * 0.8)
    await asyncio.sleep(delay)

    sent_at[order] = time.monotonic()
    await socket.send(
        json.dumps(
            {
                "type": ANSWER_SUBMIT,
                "order": order,
                "payload": build_answer(message["question"], rng),
            }
        )
    )
    result.questions_answered += 1


def _socket_status(exc: Exception) -> str:
    """A close code, named, so the failure breakdown reads as a diagnosis.

    4401/4404/4429 are the server refusing for a reason it has already
    decided; anything else is the transport, and those two want telling
    apart on the console.
    """
    # A handshake that never became a socket has an HTTP status, not a
    # close code — and "InvalidStatus" alone would send somebody hunting for a
    # protocol bug when the answer is a 403 from the origin validator.
    response = getattr(exc, "response", None)
    if response is not None:
        return f"handshake {getattr(response, 'status_code', '?')}"
    code = getattr(exc, "code", None) or getattr(
        getattr(exc, "rcvd", None), "code", None
    )
    named = {
        CLOSE_MATCHED: "4200 matched",
        CLOSE_UNAUTHENTICATED: "4401 unauthenticated",
        CLOSE_NOT_FOUND: "4404 not found",
        CLOSE_RATE_LIMITED: "4429 rate limited",
        1013: "1013 pool busy",
    }
    if code in named:
        return named[code]
    if code is not None:
        return f"close {code}"
    return type(exc).__name__
