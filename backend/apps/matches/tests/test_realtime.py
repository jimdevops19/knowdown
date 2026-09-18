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
from apps.questions.models import SingleAnswerQuestion
from apps.questions.tests.factories import make_category, make_gradual_hints
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
    async def _paired_players(self, *, category=None):
        category = category or await database_sync_to_async(stock_category)()
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

    async def test_a_question_carries_its_own_authored_time_limit(self):
        """A question authored with ``time_limit_seconds`` is broadcast with
        *that* limit, not the type's default.

        The number the client counts down from arrives in this frame and
        nowhere else — there is no per-match constant it could fall back on,
        because the limit is per question (a matrix board is authored with far
        more clock than a single-answer one). A client drawing a default over a
        45-second question would run its bar to zero with 35 seconds still on
        the server's clock, which reads to the player as the match hanging on
        their opponent.
        """
        category = await database_sync_to_async(stock_category)()
        await database_sync_to_async(
            SingleAnswerQuestion.objects.filter(category=category).update
        )(time_limit_seconds=45)

        matchup_id, sock_one, sock_two = await self._paired_players(category=category)

        # The first board reaches a socket through ``_send_current_state``...
        board_one, board_two = await _gather_json(sock_one, sock_two)
        assert board_one["type"] == events.QUESTION_STARTED
        assert board_one["time_limit_ms"] == 45_000
        assert board_two["time_limit_ms"] == 45_000

        option_id = await database_sync_to_async(_correct_option_id)(
            matchup_id=matchup_id, order=1
        )
        answer = {
            "type": events.ANSWER_SUBMIT,
            "order": 1,
            "payload": {"type": "single-answer", "option_id": option_id},
        }
        await sock_one.send_json_to(answer)
        await sock_two.send_json_to(answer)
        for _ in range(3):  # two PLAYER_ANSWERED, then the result
            await sock_one.receive_json_from(timeout=5)
            await sock_two.receive_json_from(timeout=5)

        # ...and every board after it through ``_try_close_question``'s
        # ``next``. Both paths must read the same authored value; the second is
        # the one a real player spends most of a match on.
        next_one, next_two = await _gather_json(sock_one, sock_two)
        assert next_one["type"] == events.QUESTION_STARTED
        assert next_one["order"] == 2
        assert next_one["time_limit_ms"] == 45_000
        assert next_two["time_limit_ms"] == 45_000

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

    async def test_a_deliberate_forfeit_awards_the_opponent_the_win_immediately(self):
        matchup_id, sock_one, sock_two = await self._paired_players()
        await sock_one.receive_json_from(timeout=5)
        await sock_two.receive_json_from(timeout=5)

        await sock_one.send_json_to({"type": events.FORFEIT})

        # No grace period to wait out — unlike a disconnect, a forfeit is a
        # deliberate choice, so the opponent's `MATCH_COMPLETED` follows right
        # away, with nothing between it and this send.
        completed_two = await sock_two.receive_json_from(timeout=5)
        assert completed_two["type"] == events.MATCH_COMPLETED
        assert completed_two["outcome"] == Matchup.Outcome.ABANDONED

        matchup = await database_sync_to_async(Matchup.objects.get)(pk=matchup_id)
        assert matchup.status == Matchup.Status.COMPLETED
        players = await database_sync_to_async(
            lambda: list(match_selectors.matchup_players(matchup=matchup))
        )()
        winner = next(p for p in players if p.is_winner)
        loser = next(p for p in players if not p.is_winner)
        assert str(winner.player_id) != str(loser.player_id)

        await sock_one.disconnect()
        await sock_two.disconnect()

    async def test_reconnecting_to_an_already_finished_match_gets_the_result_not_silence(self):
        # The browser-back case: a player who has already seen the result
        # screen navigates away and then back into `/match/:id`, opening a
        # fresh socket onto a matchup that finished a while ago. It must not
        # be handed a connection that only `question.started` would ever
        # unstick — there is no question left to send.
        category = await database_sync_to_async(stock_category)()
        one = await database_sync_to_async(make_player)(email="late1@example.com")
        two = await database_sync_to_async(make_player)(email="late2@example.com")

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
        await sock_one.receive_json_from(timeout=5)
        await sock_two.receive_json_from(timeout=5)

        with mock.patch("apps.matches.consumers.RECONNECT_GRACE_SECONDS", 0.2):
            await sock_one.disconnect()
            await sock_two.receive_json_from(timeout=5)  # OPPONENT_DISCONNECTED
            await sock_two.receive_json_from(timeout=10)  # MATCH_COMPLETED
        await sock_two.disconnect()

        matchup = await database_sync_to_async(Matchup.objects.get)(pk=matchup_id)
        assert matchup.status == Matchup.Status.COMPLETED

        late = await _connect_matchup(two, matchup_id)
        frame = await late.receive_json_from(timeout=5)
        assert frame["type"] == events.MATCH_COMPLETED
        assert frame["outcome"] == Matchup.Outcome.ABANDONED
        await late.disconnect()

    def tearDown(self):
        cache.clear()
        super().tearDown()


class SupersededSocketTests(TransactionTestCase):
    """The reconnect race: one player, two sockets, and the dying one's
    bookkeeping arriving last.

    Every case here is the same shape — a socket the player has already
    replaced finishes closing *after* its replacement is live — and the same
    question: does the stale socket get to speak for the player? It must not.
    The orderings are not exotic: a phone changing networks leaves the old
    socket half-open until TCP gives up, minutes after the player is back, and
    a page refresh is the same race with a shorter fuse.
    """

    async def _paired_players(self):
        category = await database_sync_to_async(stock_category)()
        one = await database_sync_to_async(make_player)(email="stale1@example.com")
        two = await database_sync_to_async(make_player)(email="stale2@example.com")

        pool_one = await _connect_matchmaking(one, category.slug)
        await pool_one.receive_json_from(timeout=5)
        pool_two = await _connect_matchmaking(two, category.slug)
        found = await pool_one.receive_json_from(timeout=5)
        await pool_two.receive_json_from(timeout=5)
        await pool_one.receive_output()
        await pool_two.receive_output()
        return found["matchup_id"], one, two

    async def test_a_stale_disconnect_does_not_abandon_a_player_who_has_reconnected(self):
        matchup_id, one, two = await self._paired_players()

        old = await _connect_matchup(one, matchup_id)
        sock_two = await _connect_matchup(two, matchup_id)
        await old.receive_json_from(timeout=5)
        await sock_two.receive_json_from(timeout=5)

        # The reconnect lands first — the player is playing again — and only
        # then does the old socket finish dying.
        new = await _connect_matchup(one, matchup_id)
        await new.receive_json_from(timeout=5)

        with mock.patch("apps.matches.consumers.RECONNECT_GRACE_SECONDS", 0.2):
            await old.disconnect()
            # Comfortably past the grace period the stale socket would have
            # armed. Waiting on ``sock_two`` for a frame instead would be the
            # trap this module's docstring warns about: a timeout there cancels
            # the consumer rather than reporting "nothing arrived".
            await asyncio.sleep(1)

        matchup = await database_sync_to_async(Matchup.objects.get)(pk=matchup_id)
        assert matchup.status == Matchup.Status.ACTIVE, (
            "a socket the player already replaced ended their match for them"
        )

        await new.disconnect()
        await sock_two.disconnect()

    async def test_the_live_socket_still_ends_the_match_when_the_player_really_leaves(self):
        """The other half of the guarantee above: refusing the *stale* socket's
        disconnect must not make the *current* one's disconnect a no-op."""
        matchup_id, one, two = await self._paired_players()

        old = await _connect_matchup(one, matchup_id)
        sock_two = await _connect_matchup(two, matchup_id)
        await old.receive_json_from(timeout=5)
        await sock_two.receive_json_from(timeout=5)
        new = await _connect_matchup(one, matchup_id)
        await new.receive_json_from(timeout=5)

        with mock.patch("apps.matches.consumers.RECONNECT_GRACE_SECONDS", 0.2):
            await old.disconnect()
            await new.disconnect()
            left = await sock_two.receive_json_from(timeout=5)
            assert left["type"] == events.OPPONENT_DISCONNECTED
            completed = await sock_two.receive_json_from(timeout=10)

        assert completed["type"] == events.MATCH_COMPLETED
        assert completed["outcome"] == Matchup.Outcome.ABANDONED
        await sock_two.disconnect()

    async def test_a_stale_disconnect_does_not_pull_a_requeued_player_out_of_the_pool(self):
        """The pool's half of the same race — and the quieter failure of the
        two: no error reaches the player, their socket stays open, and they
        simply wait in a queue they are no longer in."""
        category = await database_sync_to_async(stock_category)()
        one = await database_sync_to_async(make_player)(email="requeue@example.com")

        old = await _connect_matchmaking(one, category.slug)
        assert (await old.receive_json_from(timeout=5))["type"] == events.SEARCHING

        new = await _connect_matchmaking(one, category.slug)
        assert (await new.receive_json_from(timeout=5))["type"] == events.SEARCHING

        await old.disconnect()

        from apps.matches import pool

        assert await database_sync_to_async(pool.pool_size)(category_slug=category.slug) == 1, (
            "the replaced socket's leave_pool withdrew the live socket's claim"
        )

        # And the claim that survived is a *real* one: the next player to
        # arrive is paired with them rather than finding an empty pool.
        two = await database_sync_to_async(make_player)(email="requeue2@example.com")
        other = await _connect_matchmaking(two, category.slug)
        found = await new.receive_json_from(timeout=5)
        assert found["type"] == events.MATCH_FOUND
        await other.receive_json_from(timeout=5)
        await new.receive_output()
        await other.receive_output()
        await new.disconnect()
        await other.disconnect()

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

    def test_only_the_socket_that_holds_the_slot_may_give_it_back(self):
        """``leave_pool``'s compare-and-delete, at the unit it is decided in.

        The socket-level version of this lives in ``SupersededSocketTests``;
        this one pins the primitive, since every caller's correctness rests on
        it and a future caller that forgets to pass a token should fail here
        rather than in a player's Searching screen."""
        from apps.matches import pool

        category_slug = "token-test"
        cache.clear()

        assert pool.join_pool(category_slug=category_slug, player_id="p", join_token="old") is None
        # The reconnect: same player, new socket, taking the claim over.
        assert pool.join_pool(category_slug=category_slug, player_id="p", join_token="new") is None

        pool.leave_pool(category_slug=category_slug, player_id="p", join_token="old")
        assert pool.pool_size(category_slug=category_slug) == 1

        # The bot fallback belongs to the replaced socket too, and must not be
        # able to spend a slot that is no longer its socket's.
        assert not pool.claim_for_bot(
            category_slug=category_slug, player_id="p", join_token="old"
        )
        assert pool.pool_size(category_slug=category_slug) == 1

        assert pool.leave_pool(category_slug=category_slug, player_id="p", join_token="new")
        assert pool.pool_size(category_slug=category_slug) == 0
        cache.clear()

    def test_a_tokenless_caller_still_matches_on_the_player_id_alone(self):
        """The compatibility the token check deliberately keeps: a caller with
        no socket behind it (``apps.matches.bots``), and a slot written by a
        process that predates tokens — a rolling deploy has both shapes in one
        cache."""
        from apps.matches import pool

        category_slug = "legacy-test"
        cache.clear()

        assert pool.join_pool(category_slug=category_slug, player_id="p") is None
        assert pool.leave_pool(category_slug=category_slug, player_id="p")
        assert pool.pool_size(category_slug=category_slug) == 0

        # A legacy two-element slot, exactly as an older build wrote it.
        cache.set(pool._waiting_key(category_slug=category_slug), ("p", 1.0), timeout=60)
        assert pool.leave_pool(category_slug=category_slug, player_id="p", join_token="anything")
        assert pool.pool_size(category_slug=category_slug) == 0
        cache.clear()


def _stock_gradual_hints(*, interval_seconds: int = 1, count: int = 10):
    """A category of nothing but gradual-hints questions, revealing fast.

    One clue a second rather than the authored five, so the suite watches a
    whole reveal in about as long as one real interval. Built through the
    factory rather than the loader for the reason ``questions.tests.factories``
    exists at all — and the short interval is a *fixture*, not a loadable
    question: the schema's floor is one second and its clock check would refuse
    anything this brisk from a resource file.
    """
    category = make_category(slug="hints-only", name="Hints")
    for n in range(count):
        make_gradual_hints(
            slug=f"hinted-{n}",
            category=category,
            level=3,
            hints=(f"Clue one of {n}", f"Clue two of {n}"),
            hint_interval_seconds=interval_seconds,
        )
    return category


class GradualHintsRevealTests(TransactionTestCase):
    """The clues arrive over the socket, on the server's clock, to both sides.

    This is the type whose question is not finished being asked when the board
    lands, so the board alone proves nothing: what has to be tested is that the
    rest of it turns up, that it turns up *late*, and that it never rode along
    with the board in the first place.
    """

    async def _paired_players(self, *, category):
        one = await database_sync_to_async(make_player)(email="h1@example.com")
        two = await database_sync_to_async(make_player)(email="h2@example.com")

        pool = await _connect_matchmaking(one, category.slug)
        await pool.receive_json_from(timeout=5)
        pool2 = await _connect_matchmaking(two, category.slug)
        found = await pool.receive_json_from(timeout=5)
        await pool2.receive_json_from(timeout=5)
        await pool.receive_output()
        await pool2.receive_output()

        matchup_id = found["matchup_id"]
        # The ``Player`` rows come back with the tests: reconnecting means
        # minting a token for one of them, and resolving ``player.user`` from an
        # async test body would be a synchronous query in an event loop.
        return (
            matchup_id,
            await _connect_matchup(one, matchup_id),
            await _connect_matchup(two, matchup_id),
            one,
        )

    async def test_the_board_says_how_many_clues_are_coming_and_not_what_they_say(self):
        category = await database_sync_to_async(_stock_gradual_hints)()
        _, sock_one, sock_two, _player = await self._paired_players(category=category)

        board_one, board_two = await _gather_json(sock_one, sock_two)
        assert board_one["type"] == events.QUESTION_STARTED
        question = board_one["question"]

        # The shape of the reveal: enough to draw two empty slots and a timer.
        assert question["hint_count"] == 2
        assert question["hint_interval_ms"] == 1000
        # And none of its content, by name or by value.
        assert "hints" not in set(_walk(question))
        assert "Clue one" not in str(question)
        assert not FORBIDDEN_FIELD_NAMES & set(_walk(board_one))
        assert board_two["question"]["hint_count"] == 2

        await sock_one.disconnect()
        await sock_two.disconnect()

    async def test_every_clue_reaches_both_players(self):
        """In order, one frame each, and to both sides of the race.

        Sent per socket rather than broadcast (``consumers._HintRevealMixin``),
        so "both players saw it" is the thing that could plausibly break and is
        therefore the thing asserted — a schedule computed from the server's own
        ``started_at`` is what keeps the two in step without a broadcast.
        """
        category = await database_sync_to_async(_stock_gradual_hints)()
        _, sock_one, sock_two, _player = await self._paired_players(category=category)
        await _gather_json(sock_one, sock_two)  # the board

        for expected_index in (1, 2):
            # Generous: the first clue waits out QUESTION_READ_DELAY_SECONDS
            # with the rest of the question, because the reveal is measured from
            # the clock's zero-point and not from when the frame was dealt.
            hint_one, hint_two = await _gather_json(sock_one, sock_two, timeout=10)
            for hint in (hint_one, hint_two):
                assert hint["type"] == events.HINT_REVEALED
                assert hint["order"] == 1
                assert hint["index"] == expected_index
            assert hint_one["text"] == hint_two["text"]
            assert hint_one["text"].startswith(
                "Clue one" if expected_index == 1 else "Clue two"
            )

        await sock_one.disconnect()
        await sock_two.disconnect()

    async def test_a_reconnecting_player_is_caught_up_on_the_clues_already_due(self):
        """A refresh mid-question must not cost the clues that have gone by.

        Nothing stores which clues a player has seen — the schedule is a pure
        function of the question and ``started_at`` — so this is the same code
        path as a fresh connection, and that is exactly what makes it worth a
        test: the catch-up is a *consequence* of the design rather than a
        feature somebody remembered to add.
        """
        category = await database_sync_to_async(_stock_gradual_hints)()
        matchup_id, sock_one, sock_two, player_one = await self._paired_players(
            category=category
        )
        await _gather_json(sock_one, sock_two)

        both = await _gather_json(sock_one, sock_two, timeout=10)  # clue one
        assert both[0]["index"] == 1

        await sock_one.disconnect()
        rejoined = await _connect_matchup(player_one, matchup_id)

        # The board first, then the catch-up. ``opponent.reconnected`` goes to
        # the whole group, this socket included, so it lands somewhere in here
        # too — the clue is what is being asserted, not the frame order around
        # it.
        frames = [await rejoined.receive_json_from(timeout=5) for _ in range(3)]
        assert frames[0]["type"] == events.QUESTION_STARTED
        caught_up = next(f for f in frames if f["type"] == events.HINT_REVEALED)
        assert caught_up["type"] == events.HINT_REVEALED
        assert caught_up["index"] == 1
        assert caught_up["text"] == both[0]["text"]

        await rejoined.disconnect()
        await sock_two.disconnect()
