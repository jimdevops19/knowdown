"""The read side of the badge catalog. Never mutates, raises ``NotFound`` on a
bad lookup, the way every other app's selectors do."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.achievements.models import Achievement, PlayerAchievement
from apps.core_common.exceptions import NotFound
from apps.players.models import Player

__all__ = [
    "active_achievements",
    "get_achievement",
    "icon_url",
    "list_earned_for_player",
]


def icon_url(*, achievement: Achievement) -> str | None:
    """The badge's picture as a root-relative URL, or ``None`` — the same
    shape as ``apps.players.selectors.avatar_url``, for the same reason: the
    client is same-origin, so a relative URL travels with whichever host
    answered the request instead of baking one in."""
    if not achievement.icon:
        return None
    return achievement.icon.url


def active_achievements() -> QuerySet[Achievement]:
    """The badges that can currently be newly earned — what
    ``sync_achievements`` loaded and nobody has switched off."""
    return Achievement.objects.filter(is_active=True)


def get_achievement(*, slug: str) -> Achievement:
    try:
        return Achievement.objects.get(slug=slug)
    except Achievement.DoesNotExist as exc:
        raise NotFound(f"No achievement with slug '{slug}'.") from exc


def list_earned_for_player(*, player: Player) -> QuerySet[PlayerAchievement]:
    """A player's badge case, newest first — the read behind a public
    profile (step 19)."""
    return PlayerAchievement.objects.filter(player=player).select_related("achievement")
