"""A badge, as embedded in a public profile (step 19). There is no standalone
achievements endpoint yet — the plan asks only for what a profile shows."""

from __future__ import annotations

from rest_framework import serializers

from apps.achievements import selectors


class PlayerAchievementSerializer(serializers.Serializer):
    """One earned badge — the catalog entry plus when this player got it."""

    slug = serializers.CharField(source="achievement.slug")
    name = serializers.CharField(source="achievement.name")
    description = serializers.CharField(source="achievement.description")
    icon_url = serializers.SerializerMethodField()
    earned_at = serializers.DateTimeField()

    def get_icon_url(self, player_achievement) -> str | None:
        return selectors.icon_url(achievement=player_achievement.achievement)
