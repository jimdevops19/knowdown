"""What a player looks like on the wire.

No ``ModelSerializer`` for the writable one: the *name* is written through
``services.set_display_name`` and nowhere else, so the field here is read-only
and a PATCH that mentions it is routed to the service by the view. A
``ModelSerializer`` would happily grow a writable field the day the model grows
a column, which is the mistake this whole layer is arranged to prevent.

Nothing here carries an email address. ``GET /api/v1/auth/me/`` is the only
endpoint in the API that may, and a test walks every serializer to keep that
true (``apps.accounts.tests.test_email_exposure``).
"""

from __future__ import annotations

from rest_framework import serializers

from apps.achievements import selectors as achievement_selectors
from apps.achievements.api.serializers import PlayerAchievementSerializer
from apps.players import selectors
from apps.rankings import selectors as ranking_selectors
from apps.rankings.api.serializers import RankingSerializer


class PlayerSerializer(serializers.Serializer):
    """A competitor as anybody may see them: a name and a picture."""

    id = serializers.UUIDField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    avatar_url = serializers.SerializerMethodField()

    def get_avatar_url(self, player) -> str | None:
        return selectors.avatar_url(player=player)


class PlayerMeSerializer(PlayerSerializer):
    """The caller's own player — the public payload plus what only they need.

    ``has_auto_name`` is the client's cue to ask for a real name; nobody else
    has any use for knowing that somebody has not chosen one yet.
    """

    has_auto_name = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class PlayerProfileSerializer(PlayerSerializer):
    """``GET /api/v1/players/{display_name}/`` — the public profile: a name
    and a picture, a rating per category the player has played, and the
    badges they have earned. One round trip: ``rankings`` and ``badges`` are
    resolved from the same queries the ladder and a profile's badge case
    already use (``apps.rankings.selectors.list_rankings_for_player``,
    ``apps.achievements.selectors.list_earned_for_player``), not fetched by
    the client one at a time.
    """

    rankings = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()

    def get_rankings(self, player) -> list[dict]:
        return RankingSerializer(
            ranking_selectors.list_rankings_for_player(player=player), many=True
        ).data

    def get_badges(self, player) -> list[dict]:
        return PlayerAchievementSerializer(
            achievement_selectors.list_earned_for_player(player=player), many=True
        ).data


class DisplayNameAvailabilitySerializer(serializers.Serializer):
    """The answer to "can I have this name?" — and, when not, why not.

    ``reason`` carries the refusal code (``display_name_taken``,
    ``invalid_display_name``, ``reserved_display_name``) so the client can show
    the same message the PATCH would have given, before anybody presses save.
    """

    display_name = serializers.CharField()
    available = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)
    message = serializers.CharField(allow_null=True)
