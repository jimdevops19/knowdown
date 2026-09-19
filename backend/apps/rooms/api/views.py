"""Thin views: parse input → call one selector → serialize.

There is no write side here. Rooms come from ``resources/rooms.yaml`` via
``manage.py sync_rooms``, which is the whole point of keeping them in a
resource file — what the lobby offers is a decision made in a pull request, not
through an endpoint.
"""

from __future__ import annotations

from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from apps.rooms.api.serializers import RoomSerializer
from apps.rooms.selectors import active_rooms


class RoomListView(ListAPIView):
    """``GET /api/v1/rooms/`` — the lobby.

    ``AllowAny``, like the category list it replaces on the way in: what there
    is to play is the pitch, and there is no honest answer to "what would I be
    signing up for" that is not this list. Joining one still needs an account —
    that gate is on the matchmaking socket, where it belongs.
    """

    permission_classes = [AllowAny]
    serializer_class = RoomSerializer
    pagination_class = None  # A handful of rows; a page boundary would be noise.

    def get_queryset(self):
        return active_rooms()


class RoomDetailView(RetrieveAPIView):
    """``GET /api/v1/rooms/{slug}/``."""

    permission_classes = [AllowAny]
    serializer_class = RoomSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return active_rooms()
