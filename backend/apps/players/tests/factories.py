"""Player fixtures. Built through the services, because the services are what
guarantee the invariants the rest of the suite then leans on."""

from __future__ import annotations

from apps.accounts.models import User
from apps.players.models import Player
from apps.players.services import ensure_player_for_user

PASSWORD = "correct-horse-19"


def make_player(*, email: str = "player@example.com", display_name: str | None = None) -> Player:
    user = User.objects.create_user(email=email, password=PASSWORD)
    player = ensure_player_for_user(user=user)
    if display_name is not None:
        Player.objects.filter(pk=player.pk).update(
            display_name=display_name, has_auto_name=False
        )
        player.refresh_from_db()
    return player
