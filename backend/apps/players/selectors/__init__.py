"""Read side for the competitor. Selectors never mutate."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.core_common.exceptions import NotFound
from apps.players.models import Player


def players() -> QuerySet[Player]:
    """Every live competitor, newest first (``BaseModel.Meta.ordering``)."""
    return Player.objects.all()


def get_player(*, player_id) -> Player:
    try:
        return Player.objects.get(pk=player_id)
    except (Player.DoesNotExist, ValueError, TypeError) as exc:
        raise NotFound("Player not found.") from exc


def get_player_by_display_name(*, display_name: str) -> Player:
    """Resolve the public name to its row — how a profile URL is read.

    Case-insensitive because the uniqueness rule is: ``/players/Kobe/`` and
    ``/players/kobe/`` cannot name two people, so they must not name none.
    """
    try:
        return Player.objects.get(display_name__iexact=(display_name or "").strip())
    except Player.DoesNotExist as exc:
        raise NotFound("Player not found.") from exc


def player_for_user(*, user) -> Player | None:
    """The caller's competitor, or ``None`` for an account that has none.

    A missing reverse one-to-one raises ``RelatedObjectDoesNotExist``, which
    subclasses ``AttributeError`` — so ``getattr``'s default covers it.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "player", None)


def is_display_name_taken(*, display_name: str, exclude_player=None) -> bool:
    """Does anybody hold this name? Case-insensitive, matching the constraint."""
    taken = Player.objects.filter(display_name__iexact=(display_name or "").strip())
    if exclude_player is not None:
        taken = taken.exclude(pk=exclude_player.pk)
    return taken.exists()
