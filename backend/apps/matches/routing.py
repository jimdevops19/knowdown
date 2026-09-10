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
