"""WebSocket consumers — the transport over Phase C's already-tested rules.

A consumer here does what ``backend/CLAUDE.md`` promises: receive → validate →
call a ``apps.matches.services`` function → broadcast through ``publish.py``.
It holds no game rule of its own — every "who won this question" or "has the
match ended" decision is made by the same service function a test in
``tests/test_services.py`` calls directly, with no socket in sight. What lives
here instead is orchestration: which event fires when, and making sure a
question that nobody answers still closes.

**Server-authoritative timing survives the transport.** Each connected socket
schedules its own watchdog after a question opens (``_watch_question_timeout``)
that calls ``services.complete_question`` once the server's own clock — not
the client's — says time is up. Both players' watchdogs may fire for the same
question, and ``submit_answer`` may also close it as a side effect of the
second player's own answer; ``_try_close_question``'s ``cache.add`` mutex (the
same primitive ``apps.matches.pool`` uses for pairing) is what keeps exactly
one of those callers broadcasting the result.
"""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.core.cache import cache

from apps.categories import selectors as category_selectors
from apps.core_common.exceptions import DomainError
from apps.matches import abuse, events, groups, presence, publish
from apps.matches import selectors as match_selectors
from apps.matches import services as match_services
from apps.matches.bots import controller as bot_controller
from apps.matches.bots.selection import pick_bot_player_id
from apps.matches.constants import RECONNECT_GRACE_SECONDS, time_limit_ms_for
from apps.matches.pool import PoolTimeout, claim_for_bot, join_pool, leave_pool
from apps.players.services import ensure_player_for_user
from apps.questions.api.serializers import serialize_for_play
from apps.questions.selectors import QuestionRef
from apps.questions.selectors import get_question as get_concrete_question
from shared.logging import get_logger

logger = get_logger(__name__)

# Close codes. The 4000-4999 range is reserved for the application; a client
# tells a permanent close (stop retrying) from a transient one by the code.
# There is no separate "forbidden" code: a matchup that exists but is not
# this player's, and a matchup that does not exist at all, close identically
# (CLOSE_NOT_FOUND) — see the comment at MatchupConsumer.connect's except
# clause for why that is deliberate, not an oversight.
CLOSE_UNAUTHENTICATED = 4401
CLOSE_NOT_FOUND = 4404
CLOSE_MATCHED = 4200  # normal: the pool socket's one job is done
#: apps.matches.abuse refused this connection — too many recent joins, or too
#: many sockets already open for this account. 4429 mirrors HTTP 429 the way
#: 4401/4404 mirror their own status codes.
CLOSE_RATE_LIMITED = 4429

#: See the comment at its one call site (``MatchupConsumer.disconnect``): the
#: reconnect flag's TTL has to outlast the watchdog's own sleep, which starts
#: measuring strictly later.
_RECONNECT_FLAG_TTL_MARGIN_SECONDS = 5


async def _apublish(fn, /, **kwargs) -> None:
    """Call one of ``publish.py``'s functions from async code.

    Every ``publish.publish_*`` function is a plain synchronous function that
    reaches the channel layer through ``asgiref.sync.async_to_sync`` (see
    ``publish.py`` — it has to stay callable from ``apps.matches.services``,
    which knows nothing about async). Calling one directly from a consumer
    coroutine trips ``AsyncToSync``'s own guard against nesting inside a
    thread that already has a running event loop; running it through
    ``database_sync_to_async`` gives it the worker thread it expects, the same
    way this module already reaches every other synchronous, ORM-touching
    piece of ``apps.matches``.
    """
    await database_sync_to_async(fn)(**kwargs)


class _WatchdogMixin:
    """Shared "close a question that nobody finished answering" plumbing, and
    the background-task bookkeeping every loose task on this socket needs.

    ``asyncio`` keeps only a *weak* reference to a task created with
    ``ensure_future``/``create_task`` — nothing else holding one is exactly
    "and it may be garbage-collected mid-flight, silently, before it ever
    fires" (the behaviour is documented, and easy to never hit locally since
    GC timing hides it until it doesn't). ``_spawn`` is every place in this
    module that starts a task the consumer itself does not immediately
    ``await`` — the watchdog and the abandon-after-grace timer — routed
    through one method so the fix lives once.
    """

    def _spawn(self, coro) -> "asyncio.Task":
        # Lazily created rather than in ``__init__``: this mixin is not the
        # one that owns the consumer's constructor, and every user of it
        # needs exactly one such set regardless of where in the MRO it
        # would otherwise have to be threaded through.
        tasks = self.__dict__.setdefault("_background_tasks", set())
        task = asyncio.ensure_future(coro)
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return task

    async def _watch_question_timeout(
        self, *, matchup_id: UUID | str, order: int, time_limit_ms: int
    ) -> None:
        await asyncio.sleep(time_limit_ms / 1000 + 0.5)  # a small margin over the server clock
        await database_sync_to_async(_close_question_if_ready)(matchup_id=matchup_id, order=order)


class MatchmakingConsumer(_WatchdogMixin, AsyncJsonWebsocketConsumer):
    """One category's queue. A socket here does nothing but wait for
    ``events.MATCH_FOUND`` — the pairing itself is ``apps.matches.pool``, and
    the matchup that comes out of it is played over ``MatchupConsumer``.

    Also inherits ``_WatchdogMixin`` for its ``_spawn`` bookkeeping alone —
    the bot-fallback timer below is the one loose task this consumer starts,
    and holding it the way a question watchdog is held is what keeps it from
    being garbage-collected mid-wait (see the mixin's own docstring)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.player_id: str | None = None
        self.category_slug: str | None = None
        self._category = None
        self._matched = False
        self._registered = False

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.accept()
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return

        category_slug = self.scope["url_route"]["kwargs"]["category_slug"]
        category = await database_sync_to_async(_get_category_or_none)(slug=category_slug)
        if category is None:
            await self.accept()
            await self.close(code=CLOSE_NOT_FOUND)
            return

        player = await database_sync_to_async(ensure_player_for_user)(user=user)
        self.player_id = str(player.id)
        self.category_slug = category_slug
        self._category = category

        try:
            await database_sync_to_async(_admit_matchmaking_socket)(player_id=self.player_id)
        except abuse.RateLimited:
            await self.accept()
            await self.close(code=CLOSE_RATE_LIMITED)
            return
        self._registered = True

        await self.channel_layer.group_add(groups.player_group(self.player_id), self.channel_name)
        await self.accept()
        await database_sync_to_async(presence.set_state)(
            player_id=self.player_id, state=presence.State.SEARCHING
        )

        try:
            pairing = await database_sync_to_async(join_pool)(
                category_slug=category_slug, player_id=self.player_id
            )
        except PoolTimeout:
            logger.warning("Matchmaking pool busy — join refused", category=category_slug)
            await self.close(code=1013)  # "try again later"
            return

        if pairing is None:
            await self.send_json({"type": events.SEARCHING})
            # Journey line 1/4: "Player queued" — see CLAUDE.md's Realtime
            # section. `action` is the queryable field ("how many players
            # queued today"); the sentence is for a human tailing the log.
            logger.info(
                "Player queued for a match",
                category=category_slug,
                caller="user",
                action="queued",
            )
            if settings.FF_ENABLE_BOTS_IF_TIMEOUT:
                self._spawn(self._fall_back_to_bot_after_timeout())
            return

        await self._pair(
            category=category,
            opponent_id=pairing.opponent_id,
            opponent_queued_at=pairing.opponent_queued_at,
        )

    async def _pair(
        self, *, category, opponent_id: str, opponent_queued_at: float | None = None
    ) -> None:
        matchup_id = await database_sync_to_async(_start_matchup_for)(
            category=category, player_one_id=self.player_id, player_two_id=opponent_id
        )
        self._matched = True
        for player_id in (self.player_id, opponent_id):
            await database_sync_to_async(presence.set_state)(
                player_id=player_id, state=presence.State.MATCHED
            )
        await _apublish(publish.publish_match_found, player_id=self.player_id, matchup_id=matchup_id)
        await _apublish(publish.publish_match_found, player_id=opponent_id, matchup_id=matchup_id)
        # Journey line 2/4: "Match found". This player's own wait was ~0 (the
        # join that just happened is what completed the pairing); the
        # opponent's is the gap since they became the one waiting
        # (`pool.Pairing.opponent_queued_at`) — the number "how long did
        # players wait for an opponent" reads off of. ``None`` for a bot pair
        # (``_pair_with_bot`` below never queued an opponent to wait on).
        wait_ms = (
            None if opponent_queued_at is None
            else int((time.time() - opponent_queued_at) * 1000)
        )
        logger.info(
            "Two players were matched",
            category=self.category_slug,
            caller="user",
            action="matched",
            duration_ms=wait_ms,
        )

    async def _fall_back_to_bot_after_timeout(self) -> None:
        """``FF_ENABLE_BOTS_IF_TIMEOUT``'s whole mechanism: wait out
        ``MATCHMAKING_BOT_TIMEOUT_SECONDS``, and if this player is still the
        one waiting, claim them for a CPU opponent instead.

        ``pool.claim_for_bot`` is what makes the race with a human arriving in
        the same instant safe — see its own docstring — so the only thing
        this coroutine has to get right is not doing anything once
        ``self._matched`` is already true, which a human pairing sets before
        this sleep could plausibly still be running.
        """
        await asyncio.sleep(settings.MATCHMAKING_BOT_TIMEOUT_SECONDS)
        if self._matched:
            return

        claimed = await database_sync_to_async(claim_for_bot)(
            category_slug=self.category_slug, player_id=self.player_id
        )
        if not claimed:
            return  # a human claimed this slot, or the player already left

        bot_player_id = await database_sync_to_async(pick_bot_player_id)()
        if bot_player_id is None:
            # No bots seeded (`manage.py seed_bots`) — put the player back
            # rather than stranding them silently out of the pool.
            logger.warning(
                "Bot fallback fired with no bots seeded", category=self.category_slug
            )
            await database_sync_to_async(join_pool)(
                category_slug=self.category_slug, player_id=self.player_id
            )
            return

        await self._pair_with_bot(bot_player_id=bot_player_id)

    async def _pair_with_bot(self, *, bot_player_id: str) -> None:
        """The bot-opponent half of ``_pair``: same matchup creation, but the
        opponent has no socket to notify and needs a
        ``apps.matches.bots.controller`` task instead to play its side."""
        try:
            matchup_id = await database_sync_to_async(_start_matchup_for)(
                category=self._category, player_one_id=self.player_id, player_two_id=bot_player_id
            )
        except DomainError as exc:
            # A thin category (create_matchup drew a question_count the
            # catalog cannot fill — see questions_report) is the one way this
            # can fail once a bot has already been chosen. Logged rather than
            # raised: the player is still connected and waiting, and this is
            # exactly the case ``join_pool`` handles for a human pairing too
            # — surface it, do not leave them stranded with no explanation.
            logger.warning(
                "Bot pairing failed", category=self.category_slug, code=exc.code, reason=exc.message
            )
            await self.send_json(
                {"type": events.ERROR, "code": exc.code, "message": exc.message}
            )
            await self.close(code=1011)
            return
        self._matched = True
        await database_sync_to_async(presence.set_state)(
            player_id=self.player_id, state=presence.State.MATCHED
        )
        await _apublish(publish.publish_match_found, player_id=self.player_id, matchup_id=matchup_id)
        bot_controller.spawn_bot(
            bot_controller.run_bot(matchup_id=matchup_id, bot_player_id=bot_player_id)
        )
        # Journey line 2/4, bot variant: the player waited out the whole
        # fallback timeout (there was no human to pair with sooner) — an
        # approximation, not `pool`'s own queued_at, but close enough for
        # "how long did players wait" to read a bot pairing honestly rather
        # than as a suspiciously instant match.
        logger.info(
            "A player was matched against a CPU opponent",
            category=self.category_slug,
            caller="user",
            action="matched",
            duration_ms=settings.MATCHMAKING_BOT_TIMEOUT_SECONDS * 1000,
        )

    async def receive_json(self, content: dict, **kwargs) -> None:
        if content.get("type") == events.PING:
            await self.send_json({"type": events.PONG})
        elif content.get("type") == events.SEARCH_CANCEL:
            await self.close(code=1000)

    async def disconnect(self, code: int) -> None:
        if self._registered:
            await database_sync_to_async(abuse.unregister_socket)(player_id=self.player_id)
        if self.player_id is None:
            return
        await self.channel_layer.group_discard(groups.player_group(self.player_id), self.channel_name)
        if not self._matched:
            await database_sync_to_async(leave_pool)(
                category_slug=self.category_slug, player_id=self.player_id
            )
            await database_sync_to_async(presence.clear_presence)(player_id=self.player_id)

    # --- Channel-layer handler ------------------------------------------------
    async def match_found(self, message: dict) -> None:
        await self.send_json({"type": events.MATCH_FOUND, "matchup_id": message["matchup_id"]})
        await self.close(code=CLOSE_MATCHED)


class MatchupConsumer(_WatchdogMixin, AsyncJsonWebsocketConsumer):
    """One live matchup. Bidirectional: a player answers by sending
    ``events.ANSWER_SUBMIT`` here, the only write this socket accepts — every
    other fact about the game flows the other way, from a service call to
    ``publish.py``."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.matchup_id: str | None = None
        self.player_id: str | None = None
        self.player = None
        self._registered = False

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.accept()
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return

        matchup_id = self.scope["url_route"]["kwargs"]["matchup_id"]
        player = await database_sync_to_async(ensure_player_for_user)(user=user)

        try:
            matchup, _ = await database_sync_to_async(_get_matchup_and_side)(
                matchup_id=matchup_id, player=player
            )
        except DomainError:
            # Either the matchup does not exist, or it exists and this player
            # is not one of its two sides — both are "nothing here for you",
            # and not worth telling the two apart over a socket a stranger
            # could otherwise probe to learn which matchup ids are real.
            await self.accept()
            await self.close(code=CLOSE_NOT_FOUND)
            return

        # Checked, and registered, before any of this consumer's state is set —
        # ``disconnect`` treats a set ``self.matchup_id`` as "this player was
        # really in the match," which a refused connection must not trigger
        # (it would open the reconnect-grace/abandon path for a player who
        # never actually joined).
        try:
            await database_sync_to_async(abuse.register_socket)(player_id=str(player.id))
        except abuse.RateLimited:
            await self.accept()
            await self.close(code=CLOSE_RATE_LIMITED)
            return
        self._registered = True

        self.matchup_id = str(matchup_id)
        self.player = player
        self.player_id = str(player.id)
        await self.channel_layer.group_add(groups.matchup_group(self.matchup_id), self.channel_name)
        await self.accept()
        await database_sync_to_async(presence.set_state)(
            player_id=self.player_id, state=presence.State.PLAYING
        )

        was_disconnected = bool(cache.get(_reconnect_flag_key(self.matchup_id, self.player_id)))
        cache.delete(_reconnect_flag_key(self.matchup_id, self.player_id))
        if was_disconnected:
            await _apublish(
                publish.publish_opponent_reconnected,
                matchup_id=self.matchup_id,
                player_id=self.player_id,
            )

        await self._send_current_state(matchup)
        logger.info("A player joined a live matchup", caller="user")

    async def _send_current_state(self, matchup) -> None:
        """A reconnect's cue to resume rather than start over: the question in
        progress, the board, and how much of the server's clock is left.

        Also (re)schedules this socket's watchdog for that question. The very
        first question has nobody in the matchup group yet to hear
        ``events.QUESTION_STARTED`` broadcast — both players are still on
        their matchmaking sockets when ``start_matchup`` opens it — so the
        connecting socket has to pick up the watchdog duty itself, the same
        way the ``question_started`` group handler does for every question
        after it.
        """
        state = await database_sync_to_async(_current_state)(matchup=matchup)
        if state is not None:
            await self.send_json({"type": events.QUESTION_STARTED, **state})
            self._spawn(
                self._watch_question_timeout(
                    matchup_id=self.matchup_id, order=state["order"], time_limit_ms=state["time_limit_ms"]
                )
            )

    async def receive_json(self, content: dict, **kwargs) -> None:
        message_type = content.get("type")
        if message_type == events.PING:
            await self.send_json({"type": events.PONG})
            return
        if message_type != events.ANSWER_SUBMIT:
            return

        order = content.get("order")
        payload = content.get("payload")
        if not isinstance(order, int) or not isinstance(payload, dict):
            await self.send_json(
                {"type": events.ERROR, "code": "validation_failed", "message": "Malformed answer."}
            )
            return

        try:
            await database_sync_to_async(abuse.check_answer_submit_rate)(player_id=self.player_id)
        except abuse.RateLimited as exc:
            await self.send_json(
                {
                    "type": events.ERROR,
                    "code": "rate_limited",
                    "message": "Too many answers submitted — slow down.",
                    "retry_after": exc.retry_after,
                }
            )
            return

        try:
            await database_sync_to_async(_submit_answer)(
                matchup_id=self.matchup_id, player=self.player, order=order, payload=payload
            )
        except DomainError as exc:
            await self.send_json({"type": events.ERROR, "code": exc.code, "message": exc.message})
            return

        await _apublish(
            publish.publish_player_answered,
            matchup_id=self.matchup_id,
            order=order,
            player_id=self.player_id,
        )
        await database_sync_to_async(_close_question_if_ready)(matchup_id=self.matchup_id, order=order)

    async def disconnect(self, code: int) -> None:
        if self._registered:
            await database_sync_to_async(abuse.unregister_socket)(player_id=self.player_id)
        if self.matchup_id is None:
            return
        await self.channel_layer.group_discard(groups.matchup_group(self.matchup_id), self.channel_name)
        await database_sync_to_async(presence.clear_presence)(player_id=self.player_id)

        still_active = await database_sync_to_async(_matchup_is_active)(matchup_id=self.matchup_id)
        if not still_active:
            return

        # The TTL has to outlast ``_abandon_after_grace``'s own sleep: that
        # sleep starts *after* this line (there's an ``await`` between them),
        # so a TTL of exactly ``RECONNECT_GRACE_SECONDS`` would always have
        # expired by the time the watchdog checks it — not a race, a
        # guarantee, since the watchdog's clock starts strictly later than
        # this one. The margin only has to cover that gap, which is a couple
        # of awaits, not the grace period itself.
        cache.set(
            _reconnect_flag_key(self.matchup_id, self.player_id),
            True,
            timeout=RECONNECT_GRACE_SECONDS + _RECONNECT_FLAG_TTL_MARGIN_SECONDS,
        )
        await _apublish(
            publish.publish_opponent_disconnected,
            matchup_id=self.matchup_id,
            player_id=self.player_id,
        )
        self._spawn(self._abandon_after_grace())

    async def _abandon_after_grace(self) -> None:
        matchup_id, player_id = self.matchup_id, self.player_id
        await asyncio.sleep(RECONNECT_GRACE_SECONDS)
        if not cache.get(_reconnect_flag_key(matchup_id, player_id)):
            return  # reconnected in time — the flag was cleared on connect
        cache.delete(_reconnect_flag_key(matchup_id, player_id))
        summary = await database_sync_to_async(_abandon)(matchup_id=matchup_id, player_id=player_id)
        if summary is not None:
            await _apublish(publish.publish_match_completed, matchup_id=matchup_id, summary=summary)

    # --- Channel-layer handlers -------------------------------------------
    # Named after their ``type`` with periods swapped for underscores; Channels
    # does that mapping (see apps.matches.events for the constants).

    async def question_started(self, message: dict) -> None:
        await self.send_json(
            {
                "type": events.QUESTION_STARTED,
                "order": message["order"],
                "question": message["question"],
                "time_limit_ms": message["time_limit_ms"],
            }
        )
        self._spawn(
            self._watch_question_timeout(
                matchup_id=self.matchup_id, order=message["order"], time_limit_ms=message["time_limit_ms"]
            )
        )

    async def player_answered(self, message: dict) -> None:
        await self.send_json(
            {"type": events.PLAYER_ANSWERED, "order": message["order"], "player_id": message["player_id"]}
        )

    async def question_result(self, message: dict) -> None:
        await self.send_json(
            {"type": events.QUESTION_RESULT, "order": message["order"], "results": message["results"]}
        )

    async def match_completed(self, message: dict) -> None:
        await self.send_json({k: v for k, v in message.items()})

    async def opponent_disconnected(self, message: dict) -> None:
        await self.send_json({"type": events.OPPONENT_DISCONNECTED, "player_id": message["player_id"]})

    async def opponent_reconnected(self, message: dict) -> None:
        await self.send_json({"type": events.OPPONENT_RECONNECTED, "player_id": message["player_id"]})


# --- Sync helpers, called through database_sync_to_async ---------------------
# Plain functions rather than consumer methods: they touch only the ORM and
# apps.matches.services/selectors, so they are what a future test can call
# directly without opening a socket, the same promise Phase C made.


def _admit_matchmaking_socket(*, player_id: str) -> None:
    """Both matchmaking-specific abuse checks, in the order a refusal should
    happen: the join-rate limit first (cheapest, and the one a script hammers
    hardest by repeatedly joining and leaving), then the concurrent-socket
    budget this player shares with every ``MatchupConsumer`` they also have
    open. Raises ``apps.matches.abuse.RateLimited`` from whichever refuses."""
    abuse.check_matchmaking_join_rate(player_id=player_id)
    abuse.register_socket(player_id=player_id)


def _get_category_or_none(*, slug: str):
    try:
        return category_selectors.get_category_by_slug(slug=slug)
    except DomainError:
        return None


def _start_matchup_for(*, category, player_one_id: str, player_two_id: str) -> str:
    from apps.players.selectors import get_player

    player_one = get_player(player_id=player_one_id)
    player_two = get_player(player_id=player_two_id)
    matchup = match_services.create_matchup(category=category, player_one=player_one, player_two=player_two)
    match_services.start_matchup(matchup=matchup)
    return str(matchup.id)


def _get_matchup_and_side(*, matchup_id: str, player):
    matchup = match_selectors.get_matchup(matchup_id=matchup_id)
    matchup_player = match_selectors.get_matchup_player(matchup=matchup, player=player)
    return matchup, matchup_player


def _submit_answer(*, matchup_id: str, player, order: int, payload: dict):
    matchup = match_selectors.get_matchup(matchup_id=matchup_id)
    return match_services.submit_answer(matchup=matchup, player=player, order=order, payload=payload)


def _current_state(*, matchup) -> dict | None:
    question = match_selectors.current_question(matchup=matchup)
    if question is None:
        return None
    concrete = get_concrete_question(ref=QuestionRef(question.question_type, question.question_id))
    board = serialize_for_play(question=concrete, matchup_id=matchup.id)
    return {
        "order": question.order,
        "question": board,
        "time_limit_ms": time_limit_ms_for(
            question_type=question.question_type, override_seconds=concrete.time_limit_seconds
        ),
    }


def _matchup_is_active(*, matchup_id: str) -> bool:
    from apps.matches.models import Matchup

    matchup = match_selectors.get_matchup(matchup_id=matchup_id)
    return matchup.status == Matchup.Status.ACTIVE


def _abandon(*, matchup_id: str, player_id: str) -> dict | None:
    from apps.core_common.exceptions import Conflict
    from apps.players.selectors import get_player

    matchup = match_selectors.get_matchup(matchup_id=matchup_id)
    player = get_player(player_id=player_id)
    try:
        matchup = match_services.abandon_matchup(matchup=matchup, leaving_player=player)
    except Conflict:
        return None  # already terminal — nothing new to announce
    return _match_summary(matchup=matchup)


def _match_summary(*, matchup) -> dict:
    sides = list(match_selectors.matchup_players(matchup=matchup))
    winner = next((side for side in sides if side.is_winner), None)
    return {
        "outcome": matchup.outcome,
        "winner_player_id": str(winner.player_id) if winner else None,
        "scores": {str(side.player_id): side.score for side in sides},
    }


def _reconnect_flag_key(matchup_id: str, player_id: str) -> str:
    return f"matches:disconnect:{matchup_id}:{player_id}"


def _close_question_if_ready(*, matchup_id: str, order: int) -> None:
    """Close the question if the server's rules say it may close, and — for
    whichever caller actually wins the race to do so — broadcast what happens
    next. A no-op, quietly, for every other caller: the question was already
    closed, still open, or the matchup is already over."""
    outcome = _try_close_question(matchup_id=matchup_id, order=order)
    if outcome is None:
        return
    publish.publish_question_result(matchup_id=matchup_id, order=order, results=outcome["results"])
    if outcome["next"] is not None:
        publish.publish_question_started(
            matchup_id=matchup_id,
            order=outcome["next"]["order"],
            board=outcome["next"]["question"],
            time_limit_ms=outcome["next"]["time_limit_ms"],
        )
    if outcome["summary"] is not None:
        publish.publish_match_completed(matchup_id=matchup_id, summary=outcome["summary"])


def _try_close_question(*, matchup_id: str, order: int) -> dict | None:
    """Close question ``order`` if the server's rules allow it — whether it
    was already closed as a side effect of the second player's own
    ``submit_answer`` call, or is being closed here by a watchdog — and, for
    whichever caller wins the ``cache.add`` race below, build what to
    broadcast.

    ``complete_question`` is itself idempotent (a question already closed is
    returned unchanged rather than raising), so this never re-derives *whether*
    to close; it only decides who gets to announce it, exactly once.
    """
    from apps.matches.models import Matchup

    matchup = match_selectors.get_matchup(matchup_id=matchup_id)
    try:
        match_services.complete_question(matchup=matchup, order=order)
    except DomainError:
        return None  # still open: not every player has answered, and time remains

    if not cache.add(f"matches:broadcast:{matchup_id}:{order}", "1", timeout=60):
        return None  # another watchdog/submission already won the race to close it

    matchup.refresh_from_db()
    question = match_selectors.get_matchup_question(matchup=matchup, order=order)
    results = [
        {
            "player_id": str(answer.player_id),
            "is_correct": answer.is_correct,
            "score": answer.score,
            "points": answer.points,
            "response_time_ms": answer.response_time_ms,
        }
        for answer in question.answers.select_related("player").all()
    ]

    next_question = None
    summary = None
    if matchup.status == Matchup.Status.COMPLETED:
        summary = _match_summary(matchup=matchup)
    else:
        upcoming = match_selectors.current_question(matchup=matchup)
        if upcoming is not None and upcoming.order != order:
            upcoming_concrete = get_concrete_question(
                ref=QuestionRef(upcoming.question_type, upcoming.question_id)
            )
            board = serialize_for_play(question=upcoming_concrete, matchup_id=matchup.id)
            next_question = {
                "order": upcoming.order,
                "question": board,
                "time_limit_ms": time_limit_ms_for(
                    question_type=upcoming.question_type,
                    override_seconds=upcoming_concrete.time_limit_seconds,
                ),
            }

    return {"results": results, "next": next_question, "summary": summary}
