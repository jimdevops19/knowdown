"""The read side of a matchup — never mutates, raises ``NotFound`` on a bad
lookup, the way every other app's selectors do."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.core_common.exceptions import NotFound
from apps.matches.models import Matchup, MatchupPlayer, MatchupQuestion
from apps.players.models import Player

__all__ = [
    "current_question",
    "get_matchup",
    "get_matchup_player",
    "get_matchup_question",
    "list_matchups_for_player",
    "matchup_players",
    "opponent_of",
]


def get_matchup(*, matchup_id) -> Matchup:
    try:
        return Matchup.objects.select_related("category").get(id=matchup_id)
    except (Matchup.DoesNotExist, ValueError, TypeError) as exc:
        raise NotFound(f"No matchup with id {matchup_id}.") from exc


def matchup_players(*, matchup: Matchup) -> QuerySet[MatchupPlayer]:
    return matchup.players.select_related("player").order_by("joined_at")


def get_matchup_player(*, matchup: Matchup, player: Player) -> MatchupPlayer:
    try:
        return matchup.players.select_related("player").get(player=player)
    except MatchupPlayer.DoesNotExist as exc:
        raise NotFound(f"{player.display_name} is not a player in this matchup.") from exc


def opponent_of(*, matchup: Matchup, player: Player) -> MatchupPlayer:
    try:
        return matchup.players.select_related("player").exclude(player=player).get()
    except MatchupPlayer.DoesNotExist as exc:
        raise NotFound("This matchup has no opponent yet.") from exc


def get_matchup_question(*, matchup: Matchup, order: int) -> MatchupQuestion:
    try:
        return matchup.questions.get(order=order)
    except MatchupQuestion.DoesNotExist as exc:
        raise NotFound(f"Matchup {matchup.pk} has no question at position {order}.") from exc


def current_question(*, matchup: Matchup) -> MatchupQuestion | None:
    """The question in progress: started, not yet completed. ``None`` before
    the first question starts and after the last one completes."""
    return matchup.questions.filter(
        started_at__isnull=False, completed_at__isnull=True
    ).first()


def list_matchups_for_player(*, player: Player) -> QuerySet[Matchup]:
    """A caller's own match history, newest first — the read behind
    ``GET /api/v1/matches/``."""
    return (
        Matchup.objects.filter(players__player=player)
        .select_related("category")
        .order_by("-created_at")
        .distinct()
    )
