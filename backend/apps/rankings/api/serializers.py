"""A rating, as a client sees it — embedded in a public profile, or as one row
of a category's ladder.

``PlayerSerializer`` is imported lazily, inside ``LadderEntrySerializer.get_player``
rather than at module level: ``apps.players.api.serializers`` embeds
``RankingSerializer`` in a profile, so a top-level import back here would be a
circular one. ``RankingSerializer`` itself carries no such dependency, which is
what lets it be embedded there at all.
"""

from __future__ import annotations

from rest_framework import serializers


class RankingSerializer(serializers.Serializer):
    """One player's standing in one category — the shape a profile embeds,
    one per category they have played."""

    category = serializers.CharField(source="category.slug")
    category_name = serializers.CharField(source="category.name")
    rating = serializers.IntegerField()
    wins = serializers.IntegerField()
    losses = serializers.IntegerField()
    games_played = serializers.IntegerField()


class LadderEntrySerializer(RankingSerializer):
    """One row of ``GET /api/v1/rankings/{category}/`` — a standing plus who
    holds it. The category is redundant here (the URL already names it), but
    keeping the same shape as the profile's embed means one serializer for a
    ranking, not two."""

    player = serializers.SerializerMethodField()

    def get_player(self, ranking) -> dict:
        from apps.players.api.serializers import PlayerSerializer

        return PlayerSerializer(ranking.player).data
