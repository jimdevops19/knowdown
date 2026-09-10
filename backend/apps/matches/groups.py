"""Channel-layer group names — the addresses live updates are sent to.

Built here and nowhere else, so ``publish.py`` and ``consumers.py`` cannot
drift apart: a mismatched name is not an error anywhere, it is a socket that
stays silent, which is the most expensive kind of realtime bug to notice (the
same reasoning as rpool's ``apps.realtime.groups``).

Channels restricts a group name to ASCII letters, digits, hyphens, underscores
and periods, under 100 characters. Our primary keys are UUIDs, which already
satisfy that, so no escaping is needed.
"""

from __future__ import annotations

from uuid import UUID

MATCHUP_GROUP_PREFIX = "matchup"
PLAYER_GROUP_PREFIX = "player"


def matchup_group(matchup_id: UUID | str) -> str:
    """The group both sockets of one live matchup belong to."""
    return f"{MATCHUP_GROUP_PREFIX}.{matchup_id}"


def player_group(player_id: UUID | str) -> str:
    """One player's own channel — how ``MATCH_FOUND`` reaches a socket that is
    sitting in the matchmaking pool rather than in any matchup group yet, and
    how a matchup can reach a player's *other* connections (a second tab)."""
    return f"{PLAYER_GROUP_PREFIX}.{player_id}"
