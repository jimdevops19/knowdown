"""Presence — who is doing what, right now.

Same cache, same reasoning as ``apps.matches.pool``: Redis in a real
deployment, ``LocMemCache`` in dev/tests, and this module does not know which.
Every entry carries a TTL (``constants.PRESENCE_TTL_SECONDS``) rather than
living until explicitly cleared, so a process that dies mid-match does not
strand a player as permanently ``PLAYING`` — the next read simply finds
nothing and treats them as offline, which is the whole point of a *presence*
store instead of a *record*.
"""

from __future__ import annotations

from django.core.cache import cache

from apps.matches.constants import PRESENCE_TTL_SECONDS

__all__ = ["State", "clear_presence", "get_state", "set_state"]


class State:
    ONLINE = "online"
    SEARCHING = "searching"
    MATCHED = "matched"
    PLAYING = "playing"
    OFFLINE = "offline"


def _key(*, player_id) -> str:
    return f"presence:{player_id}"


def set_state(*, player_id, state: str, ttl: int = PRESENCE_TTL_SECONDS) -> None:
    """Stamp a player's current state, refreshing its TTL.

    Called on every transition a socket causes (connect, joined the pool,
    matched, playing) — never on a timer, so the TTL is the only thing
    standing between "the process serving this player died" and "still
    online" once nothing refreshes it.
    """
    cache.set(_key(player_id=player_id), state, timeout=ttl)


def get_state(*, player_id) -> str:
    """The player's last known state, or ``OFFLINE`` if nothing is set or the
    entry expired — the two are indistinguishable on purpose."""
    return cache.get(_key(player_id=player_id)) or State.OFFLINE


def clear_presence(*, player_id) -> None:
    """Explicit sign-off (a clean disconnect), rather than waiting on the TTL."""
    cache.delete(_key(player_id=player_id))
