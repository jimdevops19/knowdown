"""Abuse limits on answering, joining the pool, and holding sockets open.

Same posture as ``apps.accounts.tests.test_lockout``: enforcement is off in
``config.settings.test`` (see its comment), so these ask for it back with
``@override_settings`` and clear the cache themselves — the counters outlive
a test method, and a neighbouring test hammering these limits on purpose must
not inherit somebody else's count.
"""

from __future__ import annotations

import asyncio

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from apps.matches import abuse, events
from apps.matches.authentication import JWTAuthMiddlewareStack
from apps.matches.routing import websocket_urlpatterns
from apps.matches.tests.factories import stock_category
from apps.players.tests.factories import make_player

application = JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))

ENFORCED = override_settings(
    MATCH_ABUSE_LIMITS_ENFORCED=True,
    ANSWER_SUBMIT_RATE_LIMIT=3,
    ANSWER_SUBMIT_RATE_WINDOW_SECONDS=60,
    MATCHMAKING_JOIN_RATE_LIMIT=3,
    MATCHMAKING_JOIN_RATE_WINDOW_SECONDS=60,
    MAX_CONCURRENT_SOCKETS_PER_PLAYER=2,
)


@ENFORCED
class AnswerSubmitRateTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_the_first_few_submissions_cost_nothing(self):
        for _ in range(3):
            abuse.check_answer_submit_rate(player_id="player-1")

    def test_past_that_it_refuses(self):
        for _ in range(3):
            abuse.check_answer_submit_rate(player_id="player-1")
        with self.assertRaises(abuse.RateLimited) as ctx:
            abuse.check_answer_submit_rate(player_id="player-1")
        self.assertGreater(ctx.exception.retry_after, 0)

    def test_one_player_being_limited_does_not_limit_another(self):
        for _ in range(3):
            abuse.check_answer_submit_rate(player_id="player-1")
        abuse.check_answer_submit_rate(player_id="player-2")  # does not raise


@ENFORCED
class MatchmakingJoinRateTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_past_the_limit_it_refuses(self):
        for _ in range(3):
            abuse.check_matchmaking_join_rate(player_id="player-1")
        with self.assertRaises(abuse.RateLimited):
            abuse.check_matchmaking_join_rate(player_id="player-1")


@ENFORCED
class ConcurrentSocketTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_budget_not_a_rate(self):
        abuse.register_socket(player_id="player-1")
        abuse.register_socket(player_id="player-1")
        with self.assertRaises(abuse.RateLimited):
            abuse.register_socket(player_id="player-1")

    def test_releasing_a_slot_frees_it_for_the_next_connection(self):
        abuse.register_socket(player_id="player-1")
        abuse.register_socket(player_id="player-1")
        abuse.unregister_socket(player_id="player-1")
        abuse.register_socket(player_id="player-1")  # does not raise

    def test_a_refused_registration_does_not_occupy_a_slot(self):
        """The connection that gets refused never opened — its own attempt
        must not itself count toward the budget it just failed."""
        abuse.register_socket(player_id="player-1")
        abuse.register_socket(player_id="player-1")
        with self.assertRaises(abuse.RateLimited):
            abuse.register_socket(player_id="player-1")
        abuse.unregister_socket(player_id="player-1")
        abuse.register_socket(player_id="player-1")  # a real slot freed up


class CountingWithoutEnforcingTests(TestCase):
    """Enforcement off (the test-settings default): every hit is still
    counted, nobody is turned away — how the numbers become real before a
    limit starts refusing anyone."""

    def setUp(self):
        cache.clear()

    def test_nobody_is_turned_away(self):
        for _ in range(50):
            abuse.check_answer_submit_rate(player_id="player-1")
            abuse.check_matchmaking_join_rate(player_id="player-1")
            abuse.register_socket(player_id="player-1")

    def test_but_the_counters_moved(self):
        for _ in range(50):
            abuse.check_answer_submit_rate(player_id="player-1")
        count = cache.get(f"{abuse.PREFIX}:answer:player-1")
        self.assertEqual(count, 50)


class KeyNamespaceTests(SimpleTestCase):
    def test_every_key_shares_one_prefix(self):
        """A stuck counter has to be findable, and droppable, without knowing
        which player it belongs to."""
        self.assertTrue(abuse._socket_count_key("player-1").startswith(abuse.PREFIX))


@override_settings(MATCH_ABUSE_LIMITS_ENFORCED=True, MAX_CONCURRENT_SOCKETS_PER_PLAYER=1)
class ConcurrentSocketOverTheWireTests(TransactionTestCase):
    """The budget as a live consumer actually enforces it — not just the
    module underneath."""

    def setUp(self):
        cache.clear()

    async def test_a_second_socket_for_the_same_account_is_refused(self):
        category = await asyncio.get_event_loop().run_in_executor(None, stock_category)
        player = await asyncio.get_event_loop().run_in_executor(
            None, lambda: make_player(email="two-tabs@example.com")
        )
        token = AccessToken.for_user(player.user)

        first = WebsocketCommunicator(
            application, f"/ws/v1/matchmaking/{category.slug}/?token={token}"
        )
        connected, _ = await first.connect()
        self.assertTrue(connected)
        self.assertEqual((await first.receive_json_from(timeout=5))["type"], events.SEARCHING)

        second = WebsocketCommunicator(
            application, f"/ws/v1/matchmaking/{category.slug}/?token={token}"
        )
        connected, _ = await second.connect()
        self.assertTrue(connected)  # the socket opens; the app-level close follows
        close = await second.receive_output(timeout=5)
        self.assertEqual(close["type"], "websocket.close")
        from apps.matches.consumers import CLOSE_RATE_LIMITED

        self.assertEqual(close["code"], CLOSE_RATE_LIMITED)

        await first.disconnect()
        await second.disconnect()
