"""WebSocket URL map — the ``/ws/`` counterpart to ``config.urls``.

Versioned like the REST API (``/ws/v1/``) and for the same reason: the message
shapes in ``events.py`` are a published contract with a deployed client, and a
breaking change to them needs somewhere to live that does not break the tab
already open.
"""

from __future__ import annotations

from django.urls import path

from .consumers import MatchmakingConsumer, MatchupConsumer

websocket_urlpatterns = [
    # The lobby's queue: a player joins a **room** (``apps.rooms``), which is
    # the set of settings a match there is played under. Listed first, and on
    # its own ``room/`` segment, so it can never be shadowed by the category
    # route below — ``<slug:category_slug>`` would happily swallow the literal
    # word "room" as a category name.
    path(
        "ws/v1/matchmaking/room/<slug:room_slug>/",
        MatchmakingConsumer.as_asgi(),
        name="ws-matchmaking-room",
    ),
    # The original route, kept: a category is still a legitimate thing to queue
    # for (the rehearsal fixtures do, and a client that predates rooms still
    # does), and a published URL is a contract with a tab that is already open.
    # Both routes reach the same consumer; the difference is one lookup — see
    # ``consumers._PoolTarget``.
    path(
        "ws/v1/matchmaking/<slug:category_slug>/",
        MatchmakingConsumer.as_asgi(),
        name="ws-matchmaking",
    ),
    path(
        "ws/v1/matches/<uuid:matchup_id>/",
        MatchupConsumer.as_asgi(),
        name="ws-matchup",
    ),
]
