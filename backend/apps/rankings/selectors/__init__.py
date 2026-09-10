"""The read side of the ladder — never mutates, raises ``NotFound`` on a bad
lookup, the way every other app's selectors do."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.categories.models import Category
from apps.core_common.exceptions import NotFound
from apps.players.models import Player
from apps.rankings.models import Ranking

__all__ = [
    "get_ranking",
    "ladder",
    "list_rankings_for_player",
    "unrated_players",
]


def get_ranking(*, player: Player, category: Category) -> Ranking:
    try:
        return Ranking.objects.select_related("player", "category").get(
            player=player, category=category
        )
    except Ranking.DoesNotExist as exc:
        raise NotFound(
            f"{player.display_name} has no ranking in {category.slug}."
        ) from exc


def ladder(*, category: Category) -> QuerySet[Ranking]:
    """A category's standings, highest rating first — one query, not one per
    row: ``select_related`` folds the player join into it, and the index on
    ``(category, -rating)`` (``models.Ranking.Meta``) is what it walks.

    Excludes bots (``player__is_bot``): a CPU opponent's matchups never move
    its rating (``apps.matches.models.Matchup.is_ranked``), so a bot sitting
    at the unmoved ``DEFAULT_PLAYER_RATING`` would either clutter the top of
    a fresh ladder or read as a real player's actual standing — neither of
    which it is.
    """
    return (
        Ranking.objects.filter(category=category, player__is_bot=False)
        .select_related("player")
        .order_by("-rating")
    )


def list_rankings_for_player(*, player: Player) -> QuerySet[Ranking]:
    """Every category a player has a rating in — the read behind a profile
    (step 19)."""
    return Ranking.objects.filter(player=player).select_related("category")


def unrated_players(*, category: Category) -> QuerySet[Player]:
    """Players with no ``Ranking`` row in ``category`` yet — who
    ``backfill_rankings`` still has to seed. Excludes bots: a CPU opponent is
    never ranked (``apps.matches.models.Matchup.is_ranked``), so backfilling
    one a row would only have to sit there unmoved forever."""
    return Player.objects.filter(is_bot=False).exclude(rankings__category=category)
