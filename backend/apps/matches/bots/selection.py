"""Which bot stands in for a missing second human.

Deliberately not skill-matched to the waiting player's own rating: a rating
comparison would need this module to import ``apps.rankings``, and
matchmaking's bot fallback exists to unblock someone with nobody else online,
not to referee a fair fight. A future pass that wants matched difficulty can
read ``BotProfile.accuracy`` the same way a leaderboard reads ``Ranking`` —
nothing here forecloses it.
"""

from __future__ import annotations

import random

from apps.players.models import Player

__all__ = ["pick_bot_player_id"]


def pick_bot_player_id() -> str | None:
    """A random active bot's player id, or ``None`` if the roster is empty
    (``manage.py seed_bots`` has not been run). ``None`` is not an error —
    the caller (``apps.matches.consumers``) puts the waiting player back in
    the pool rather than failing their search."""
    ids = list(Player.objects.filter(is_bot=True).values_list("id", flat=True))
    if not ids:
        return None
    return str(random.choice(ids))
