"""Phase D, end to end: two real sockets, no shortcuts through ``services``.

``channels.testing.WebsocketCommunicator`` drives the actual ``consumers.py``
against the actual channel layer (in-memory, per ``config.settings.test``), so
these tests exercise exactly what a client would: connect, get paired, play a
full match, and disconnect. The application under test omits
``AllowedHostsOriginValidator`` — that check belongs to ``config.asgi`` and is
about which *browser origins* may open a socket at all, a concern orthogonal to
whether the consumers behave, and the communicator sends no ``Origin`` header
for the same reason a curl script would not.

**Never poll a communicator with a short timeout expecting a miss to be
harmless.** ``asgiref.testing.ApplicationCommunicator.receive_output``
*cancels* the consumer's underlying task the moment its wait times out —
a timeout is not "nothing arrived yet, ask again," it is "this socket is
done." Every wait below uses one timeout long enough to cover what it is
actually waiting for, once.
"""

from __future__ import annotations

import asyncio
from unittest import mock

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import TransactionTestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.matches import events
from apps.matches import selectors as match_selectors
from apps.matches.authentication import JWTAuthMiddlewareStack
from apps.matches.models import Matchup
from apps.matches.routing import websocket_urlpatterns
from apps.matches.tests.factories import stock_category
from apps.players.tests.factories import make_player
from apps.questions.api.serializers import FORBIDDEN_FIELD_NAMES
from apps.questions.selectors import QuestionRef
from apps.questions.selectors import get_question as get_concrete_question

application = JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))


def _correct_option_id(*, matchup_id, order: int) -> int:
    """The right answer, read from the database the way ``test_services.py``
    does (``_correct_option_id``) — never from the served board, whose options
    are shuffled per matchup (``questions.api.serializers.shuffle_seed``) and
    carry no ``is_correct`` flag to read in the first place."""
    matchup = Matchup.objects.get(pk=matchup_id)
    question = match_selectors.get_matchup_question(matchup=matchup, order=order)
    concrete = get_concrete_question(ref=QuestionRef(question.question_type, question.question_id))
    return concrete.options.get(is_correct=True).id


def _token_query(player) -> str:
    token = AccessToken.for_user(player.user)
    return f"?token={token}"


async def _connect_matchmaking(player, category_slug: str) -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(
        application, f"/ws/v1/matchmaking/{category_slug}/{_token_query(player)}"
    )
    connected, _ = await communicator.connect()
    assert connected
    return communicator


async def _gather_json(*communicators: WebsocketCommunicator, timeout: int = 5) -> list:
    """Receive one JSON frame from each communicator concurrently.

    Awaiting them one at a time (``await a.receive_json_from(); await
    b.receive_json_from()``) makes the second wait for a message that a
    *different* consumer's own asyncio task — not this one — is what
    delivers, and under this project's test runner (``TestCase`` wraps an
    async test method in ``asgiref.sync.async_to_sync``) that task is not
    guaranteed to be scheduled before the first ``await`` above it returns.
    Gathering both is what actually interleaves them.
    """
    return list(await asyncio.gather(*(c.receive_json_from(timeout=timeout) for c in communicators)))


async def _connect_matchup(player, matchup_id) -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(
        application, f"/ws/v1/matches/{matchup_id}/{_token_query(player)}"
    )
    connected, _ = await communicator.connect()
    assert connected
    return communicator


def _walk(payload):
    """Every string key in a nested structure, lower-cased — the same
    walk-every-field posture ``questions.tests.test_serializers`` takes."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield key.lower()
            yield from _walk(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk(item)


class MatchmakingPairingTests(TransactionTestCase):
    async def test_two_players_are_paired_and_a_matchup_starts(self):
        category = await database_sync_to_async(stock_category)()
        one = await database_sync_to_async(make_player)(email="one@example.com")
        two = await database_sync_to_async(make_player)(email="two@example.com")

        first = await _connect_matchmaking(one, category.slug)
        assert (await first.receive_json_from(timeout=5))["type"] == events.SEARCHING

        second = await _connect_matchmaking(two, category.slug)

        found_first = await first.receive_json_from(timeout=5)
        found_second = await second.receive_json_from(timeout=5)
        assert found_first["type"] == events.MATCH_FOUND
        assert found_first["matchup_id"] == found_second["matchup_id"]

        matchup = await database_sync_to_async(Matchup.objects.get)(pk=found_first["matchup_id"])
        assert matchup.status == Matchup.Status.ACTIVE
        assert matchup.category_id == category.id

        # The pairing socket's job is done — it closes itself.
        await first.receive_output()
        await second.receive_output()
        await first.disconnect()
        await second.disconnect()


class MatchupPlayTests(TransactionTestCase):
    async def _paired_players(self):
        category = await database_sync_to_async(stock_category)()
        one = await database_sync_to_async(make_player)(email="p1@example.com")
        two = await database_sync_to_async(make_player)(email="p2@example.com")

        pool = await _connect_matchmaking(one, category.slug)
        await pool.receive_json_from(timeout=5)
        pool2 = await _connect_matchmaking(two, category.slug)
        found = await pool.receive_json_from(timeout=5)
        await pool2.receive_json_from(timeout=5)
        await pool.receive_output()
        await pool2.receive_output()

        matchup_id = found["matchup_id"]
        sock_one = await _connect_matchup(one, matchup_id)
        sock_two = await _connect_matchup(two, matchup_id)
        return matchup_id, sock_one, sock_two

    async def test_full_match_plays_to_a_winner_over_the_sockets(self):
        matchup_id, sock_one, sock_two = await self._paired_players()

        # Read both sockets concurrently throughout — never one, then the
        # other — so the test never blocks on one socket's queue while the
        # other consumer's still-in-flight ``connect()``/handler continuation
        # (a separate asyncio task) is what would actually deliver it.
        board_one, board_two = await _gather_json(sock_one, sock_two)
        order = 1
        while True:
            assert board_one["type"] == events.QUESTION_STARTED
            assert board_one["order"] == order == board_two["order"]

            # Anti-cheat: nothing before QUESTION_RESULT may name the answer.
            leaked = FORBIDDEN_FIELD_NAMES & set(_walk(board_one))
            assert not leaked, f"question.started leaked {leaked}"

            option_id = await database_sync_to_async(_correct_option_id)(matchup_id=matchup_id, order=order)
            answer = {
                "type": events.ANSWER_SUBMIT,
                "order": order,
                "payload": {"type": "single-answer", "option_id": option_id},
            }
            await sock_one.send_json_to(answer)
            await sock_two.send_json_to(answer)

            # Each socket sees: two PLAYER_ANSWERED, then the result, then
            # either the next board or the match's end.
            one_msgs = [await sock_one.receive_json_from(timeout=5) for _ in range(3)]
            two_msgs = [await sock_two.receive_json_from(timeout=5) for _ in range(3)]
            assert [m["type"] for m in one_msgs[:2]] == [events.PLAYER_ANSWERED] * 2
            assert [m["type"] for m in two_msgs[:2]] == [events.PLAYER_ANSWERED] * 2

            result_one = one_msgs[2]
            assert result_one["type"] == events.QUESTION_RESULT
            assert len(result_one["results"]) == 2
            assert all(r["is_correct"] for r in result_one["results"])

            board_one, board_two = await _gather_json(sock_one, sock_two)
            if board_one["type"] == events.MATCH_COMPLETED:
                assert board_one["outcome"] == Matchup.Outcome.PLAYED
                break
            order += 1

        await sock_one.disconnect()
        await sock_two.disconnect()

    async def test_a_question_nobody_answers_still_closes(self):
        # Both the watchdog's own clock (consumers) and the deadline the
        # service checks against (services) read ``time_limit_ms_for`` from
        # ``apps.matches.constants`` at call time, so patching the one
        # default it falls back to is enough to make both agree time has run
        # out immediately.
        with mock.patch("apps.matches.constants.FALLBACK_QUESTION_TIME_LIMIT_MS", 0):
            matchup_id, sock_one, sock_two = await self._paired_players()
            await sock_one.receive_json_from(timeout=5)
            await sock_two.receive_json_from(timeout=5)

            outcome = await sock_one.receive_json_from(timeout=5)
            assert outcome["type"] == events.QUESTION_RESULT
            assert outcome["results"] == []  # nobody answered — nothing to score

        await sock_one.disconnect()
        await sock_two.disconnect()

    async def test_a_disconnect_mid_match_awards_the_win_after_the_grace_period(self):
        matchup_id, sock_one, sock_two = await self._paired_players()
        await sock_one.receive_json_from(timeout=5)
        await sock_two.receive_json_from(timeout=5)

        # Not 0: the same constant also backs the cache flag's TTL
        # (``consumers.disconnect``), and a zero timeout there means "already
        # expired", which would make ``_abandon_after_grace`` see nothing to
        # wait on and give up early rather than actually award the win.
        with mock.patch("apps.matches.consumers.RECONNECT_GRACE_SECONDS", 0.2):
            await sock_one.disconnect()
            left = await sock_two.receive_json_from(timeout=5)
            assert left["type"] == events.OPPONENT_DISCONNECTED

            completed = await sock_two.receive_json_from(timeout=10)

        assert completed["type"] == events.MATCH_COMPLETED
        assert completed["outcome"] == Matchup.Outcome.ABANDONED

        matchup = await database_sync_to_async(Matchup.objects.get)(pk=matchup_id)
        assert matchup.status == Matchup.Status.COMPLETED
        await sock_two.disconnect()

    def tearDown(self):
        cache.clear()
        super().tearDown()


class MatchmakingPoolTests(TransactionTestCase):
    """The atomic-pairing guarantee, without a socket — the primitive
    ``apps.matches.pool`` exists to name (``plan.md`` step 14)."""

    def test_concurrent_joins_each_land_in_exactly_one_pairing(self):
        from concurrent.futures import ThreadPoolExecutor

        from apps.matches import pool

        category_slug = "concurrency-test"
        cache.clear()
        player_ids = [f"player-{i}" for i in range(20)]

        def join(player_id):
            return pool.join_pool(category_slug=category_slug, player_id=player_id)

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(join, player_ids))

        paired = [r for r in results if r is not None]
        # A ``None`` result means "you are the one waiting *right now*" — a
        # transient state, not a final one. With the pool serialized one join
        # at a time (the module docstring's guarantee), each successful
        # pairing consumes exactly one earlier ``None`` (its first half) and
        # produces exactly one ``Pairing`` (its second half), so for an even
        # number of players every ``None`` is eventually claimed and none are
        # left over.
        became_the_waiter = {player_ids[i] for i, r in enumerate(results) if r is None}
        opponents_named = {r.opponent_id for r in paired}

        # Every opponent named is someone who was, at some point, the one
        # waiting — and each such player is named exactly once: an opponent
        # named twice would mean two matchups sharing one player.
        assert opponents_named <= became_the_waiter
        assert len(opponents_named) == len(paired)
        assert opponents_named == became_the_waiter  # 20 players, 0 left over
        assert pool.pool_size(category_slug=category_slug) == 0
        cache.clear()
