"""What a room looks like to a client.

The lobby's payload, and deliberately more than the room's own columns: a
player deciding which circle to tap wants to know what is *in* the room (which
sports, narrowed how) and how long a game there runs. Both are computed from
rows the client should never have to assemble itself.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.rooms.models import Room, RoomCategory
from apps.rooms.selectors import room_pool_size


class RoomCategorySerializer(serializers.ModelSerializer):
    """One category a room draws from, as a client sees it."""

    slug = serializers.SlugField(source="category.slug", read_only=True)
    name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = RoomCategory
        fields = ("slug", "name", "filter_tags")
        read_only_fields = fields


class RoomSerializer(serializers.ModelSerializer):
    """A room as a client sees it.

    ``id`` is deliberately absent, for the reason ``CategorySerializer`` gives:
    the slug is the identifier the API takes and answers with, and exposing a
    second one invites clients to key on the UUID and then break when the room
    is reloaded from its resource file.
    """

    #: The authored ``questions_asked_ranges``, under the name the rest of the
    #: platform uses for it. A client shows this as "4, 5 or 6 questions".
    question_counts = serializers.ListField(
        source="question_count_choices", child=serializers.IntegerField(), read_only=True
    )

    categories = RoomCategorySerializer(many=True, read_only=True)

    #: How many questions the room can currently draw from. The lobby uses it
    #: to tell a playable room from one whose filters have outrun the catalog —
    #: which is a thing to say *before* somebody joins the queue, since
    #: ``select_room_questions`` refuses rather than playing a shorter match.
    question_pool_size = serializers.SerializerMethodField()

    #: Whether a match here moves a ladder (``Room.is_rated``) — false for a
    #: room drawing from more than one category. Sent rather than left for the
    #: client to infer from ``categories``: the rule for what counts as rated
    #: is the server's, and a client re-deriving it is a second copy to keep in
    #: step. Reads the prefetched categories, so it costs no extra query.
    is_rated = serializers.BooleanField(read_only=True)

    class Meta:
        model = Room
        fields = (
            "slug",
            "name",
            "description",
            "question_counts",
            "categories",
            "question_pool_size",
            "is_rated",
            "logo",
            "color",
        )
        read_only_fields = fields

    def get_question_pool_size(self, room: Room) -> int:
        return room_pool_size(room=room)
