"""Queuing for a **room** over the matchmaking socket.

The category route has its own coverage in ``apps.matches.tests.test_realtime``
and is unchanged; what is asserted here is the part rooms added — that the room
URL pairs, that the matchup it produces carries the room's settings, and that
the two routes are genuinely separate queues.
"""

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.matches import events
from apps.matches.models import Matchup
from apps.matches.tests.factories import stock_category
from apps.players.tests.factories import make_player
from apps.questions.tests.factories import make_category
from apps.matches.authentication import JWTAuthMiddlewareStack
from apps.matches.routing import websocket_urlpatterns
from apps.rooms.tests.factories import make_room

#: The same stack ``apps.matches.tests.test_realtime`` drives, and omitting
#: ``AllowedHostsOriginValidator`` for the same reason: that check belongs to
#: ``config.asgi`` and is about which browser *origins* may open a socket,
#: which is orthogonal to whether the consumer behaves — and the communicator
#: sends no ``Origin`` header, so leaving it in refuses every connection here.
application = JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))


def _token_query(player) -> str:
    return f"?token={AccessToken.for_user(player.user)}"


async def _connect_room(player, room_slug: str) -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(
        application, f"/ws/v1/matchmaking/room/{room_slug}/{_token_query(player)}"
    )
    connected, _ = await communicator.connect()
    assert connected
    return communicator


async def _connect_category(player, category_slug: str) -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(
        application, f"/ws/v1/matchmaking/{category_slug}/{_token_query(player)}"
    )
    connected, _ = await communicator.connect()
    assert connected
    return communicator


class RoomMatchmakingTests(TransactionTestCase):
    async def test_two_players_in_a_room_are_paired_and_the_match_carries_it(self):
        category = await database_sync_to_async(stock_category)()
        room = await database_sync_to_async(make_room)(
            slug="finals-room", counts=[4], categories=[(category, {})]
        )
        one = await database_sync_to_async(make_player)(email="one@example.com")
        two = await database_sync_to_async(make_player)(email="two@example.com")

        first = await _connect_room(one, room.slug)
        assert (await first.receive_json_from(timeout=5))["type"] == events.SEARCHING
        second = await _connect_room(two, room.slug)

        found_first = await first.receive_json_from(timeout=5)
        found_second = await second.receive_json_from(timeout=5)
        assert found_first["type"] == events.MATCH_FOUND
        assert found_first["matchup_id"] == found_second["matchup_id"]

        matchup = await database_sync_to_async(Matchup.objects.get)(
            pk=found_first["matchup_id"]
        )
        assert matchup.room_id == room.id
        # The room's rating scope, and the room's own match length — neither of
        # which the socket said, and both of which the room decided.
        assert matchup.category_id == category.id
        assert matchup.question_count == 4

        await first.receive_output()
        await second.receive_output()
        await first.disconnect()
        await second.disconnect()

    async def test_an_unknown_room_is_closed_not_queued(self):
        player = await database_sync_to_async(make_player)(email="lost@example.com")
        communicator = WebsocketCommunicator(
            application, f"/ws/v1/matchmaking/room/nope/{_token_query(player)}"
        )
        connected, _ = await communicator.connect()
        assert connected
        assert (await communicator.receive_output(timeout=5))["type"] == "websocket.close"
        await communicator.disconnect()

    async def test_an_inactive_room_is_closed_too(self):
        """A lobby loaded ten minutes ago can still offer a room since parked."""
        category = await database_sync_to_async(stock_category)()
        await database_sync_to_async(make_room)(
            slug="parked", is_active=False, categories=[(category, {})]
        )
        player = await database_sync_to_async(make_player)(email="late@example.com")
        communicator = WebsocketCommunicator(
            application, f"/ws/v1/matchmaking/room/parked/{_token_query(player)}"
        )
        connected, _ = await communicator.connect()
        assert connected
        assert (await communicator.receive_output(timeout=5))["type"] == "websocket.close"
        await communicator.disconnect()

    async def test_a_room_and_a_same_named_category_are_different_queues(self):
        """The pool's keys are namespaced — a player waiting in a room must
        never be handed to one waiting in a category."""
        category = await database_sync_to_async(stock_category)(
            category=await database_sync_to_async(make_category)(slug="nba", name="NBA")
        )
        room = await database_sync_to_async(make_room)(
            slug="nba", name="NBA Room", counts=[3], categories=[(category, {})]
        )
        one = await database_sync_to_async(make_player)(email="room@example.com")
        two = await database_sync_to_async(make_player)(email="cat@example.com")

        in_room = await _connect_room(one, room.slug)
        assert (await in_room.receive_json_from(timeout=5))["type"] == events.SEARCHING
        in_category = await _connect_category(two, category.slug)
        # Still searching, not matched: the two are in different pools.
        assert (await in_category.receive_json_from(timeout=5))["type"] == events.SEARCHING

        await in_room.disconnect()
        await in_category.disconnect()
