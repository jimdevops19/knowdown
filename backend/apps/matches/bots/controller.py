"""Drives a bot's side of one live matchup.

``run_bot`` is spawned once, by ``apps.matches.consumers.MatchmakingConsumer``,
the moment a human is paired against a CPU opponent instead of a second human
— see the module docstring on ``apps.matches.bots`` and ``Knowdown-ARCH.md``
for the fallback that gets it there. From that point on a bot needs no socket
of its own: it polls the matchup for the question currently open, sleeps until
its own chosen response time, then calls ``apps.matches.services.submit_answer``
exactly as ``consumers._submit_answer`` would for a real client's
``ANSWER_SUBMIT`` frame, and reuses ``consumers._close_question_if_ready`` to
broadcast the result — the same one-broadcaster-wins mutex a human's own
watchdog or the opponent's submission would race against.

**Polling, not a channel-layer subscription.** A human's consumer discovers a
new question by receiving ``events.QUESTION_STARTED`` on the group it joined;
a bot has no consumer to receive it on. ``_POLL_INTERVAL_SECONDS`` is short
enough that the extra latency it adds is well inside the noise already in a
bot's own response-time band, and it keeps this module free of the
channel-layer plumbing a fake consumer would otherwise need.

**Task lifetime, the same concern ``consumers._WatchdogMixin`` documents.** A
task created with ``asyncio.ensure_future`` and held by nothing is eligible for
silent garbage collection mid-flight. A bot's task must outlive the *human's*
consumer that spawned it (which disconnects almost immediately — its one job,
finding the game, is already done) rather than being tied to that consumer's
own lifetime, so it is tracked in a module-level set here instead of
``_WatchdogMixin``'s per-instance one.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from channels.db import database_sync_to_async
from django.utils import timezone

from apps.core_common.exceptions import DomainError
from apps.matches import publish
from apps.matches import selectors as match_selectors
from apps.matches import services as match_services
from apps.matches.constants import time_limit_ms_for
from apps.matches.models import BotProfile, Matchup, PlayerAnswer
from apps.questions.selectors import QuestionRef
from apps.questions.selectors import get_question as get_concrete_question
from shared.logging import get_logger

from .answering import build_bot_answer

logger = get_logger(__name__)

__all__ = ["run_bot", "spawn_bot"]

#: How often a bot checks whether a new question has opened. Not the bot's
#: *response* time — that is ``BotProfile``'s own band — just the granularity
#: this loop notices one has started at all.
_POLL_INTERVAL_SECONDS = 0.35

#: A margin kept before a question's own deadline: a bot's target response
#: time is clamped to land at least this long before the clock the server's
#: own watchdogs/``complete_question`` will close the question on, so a slow
#: bot is scored as a real (late but valid) answer rather than losing a race
#: against its own submission being refused as already-closed.
_DEADLINE_MARGIN_MS = 250

_bot_tasks: set[asyncio.Task] = set()


def spawn_bot(coro) -> asyncio.Task:
    """Schedule ``coro`` and hold a strong reference to it until it finishes —
    see the module docstring for why this cannot reuse
    ``consumers._WatchdogMixin._spawn``."""
    task = asyncio.ensure_future(coro)
    _bot_tasks.add(task)
    task.add_done_callback(_bot_tasks.discard)
    return task


async def run_bot(*, matchup_id: str, bot_player_id: str) -> None:
    """One bot's whole game, start to finish. Returns once the matchup is no
    longer active — completed, abandoned, or (defensively) never found."""
    profile = await database_sync_to_async(_get_profile)(bot_player_id=bot_player_id)
    if profile is None:
        logger.warning("Bot has no BotProfile — cannot play")
        return

    answered_or_skipped: set[int] = set()
    while True:
        state = await database_sync_to_async(_next_state)(
            matchup_id=matchup_id,
            bot_player_id=bot_player_id,
            profile=profile,
            done_orders=answered_or_skipped,
        )
        if state is None:
            return
        if isinstance(state, _Skip):
            answered_or_skipped.add(state.order)
            continue
        if isinstance(state, _Wait):
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            continue

        await asyncio.sleep(state.delay_seconds)
        await database_sync_to_async(_submit)(
            matchup_id=matchup_id, bot_player_id=bot_player_id, order=state.order, profile=profile
        )
        answered_or_skipped.add(state.order)
        await database_sync_to_async(publish.publish_player_answered)(
            matchup_id=matchup_id, order=state.order, player_id=bot_player_id
        )
        # Imported lazily: apps.matches.consumers imports apps.matches.pool at
        # module load, and importing it back at module scope here would be a
        # cycle for no reason this call needs paid up front.
        from apps.matches.consumers import _close_question_if_ready

        await database_sync_to_async(_close_question_if_ready)(matchup_id=matchup_id, order=state.order)


# --- Sync helpers, called through database_sync_to_async --------------------


@dataclass(frozen=True)
class _Wait:
    """Nothing to do yet — no question open, or its clock hasn't started."""


@dataclass(frozen=True)
class _Skip:
    """This order needs no action from the bot (already answered, already
    closed, or too little time remains to answer honestly)."""

    order: int


@dataclass(frozen=True)
class _Answer:
    """Sleep ``delay_seconds`` more, then submit for ``order``."""

    order: int
    delay_seconds: float


def _get_profile(*, bot_player_id: str) -> BotProfile | None:
    return BotProfile.objects.filter(player_id=bot_player_id).select_related("player").first()


def _next_state(
    *, matchup_id: str, bot_player_id: str, profile: BotProfile, done_orders: set[int]
) -> _Wait | _Skip | _Answer | None:
    matchup = match_selectors.get_matchup(matchup_id=matchup_id)
    if matchup.status != Matchup.Status.ACTIVE:
        return None

    question = match_selectors.current_question(matchup=matchup)
    if question is None:
        return _Wait()
    if question.order in done_orders:
        return _Wait()
    if question.started_at is None:
        return _Wait()
    if question.completed_at is not None:
        return _Skip(question.order)
    if PlayerAnswer.objects.filter(matchup_question=question, player_id=bot_player_id).exists():
        return _Skip(question.order)

    concrete = get_concrete_question(ref=QuestionRef(question.question_type, question.question_id))
    time_limit_ms = time_limit_ms_for(
        question_type=question.question_type, override_seconds=concrete.time_limit_seconds
    )
    elapsed_ms = (timezone.now() - question.started_at).total_seconds() * 1000
    deadline_ms = time_limit_ms - _DEADLINE_MARGIN_MS
    if elapsed_ms >= deadline_ms:
        return _Skip(question.order)  # too late to land an honest answer — let it time out

    target_ms = min(random.uniform(profile.min_response_ms, profile.max_response_ms), deadline_ms)
    return _Answer(order=question.order, delay_seconds=max(0.0, (target_ms - elapsed_ms) / 1000))


def _submit(*, matchup_id: str, bot_player_id: str, order: int, profile: BotProfile) -> None:
    matchup = match_selectors.get_matchup(matchup_id=matchup_id)
    question = match_selectors.get_matchup_question(matchup=matchup, order=order)
    if question.completed_at is not None:
        return  # closed while the bot was "thinking" — the human got there first

    concrete = get_concrete_question(
        ref=QuestionRef(question.question_type, question.question_id)
    )
    payload = build_bot_answer(question=concrete, correct=random.random() < profile.accuracy)
    try:
        match_services.submit_answer(
            matchup=matchup, player=profile.player, order=order, payload=payload
        )
    except DomainError as exc:
        logger.warning("Bot answer submission refused", reason=str(exc))
