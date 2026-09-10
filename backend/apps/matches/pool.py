"""The global matchmaking pool — one logical queue per category, in the cache.

**No database row per waiting player.** ``PostgreSQL`` stores what happened;
this stores who is, right now, looking for a game — the same split
``config.settings.base`` draws for ``CHANNEL_LAYERS``. It rides
``django.core.cache.cache`` rather than a hand-rolled Redis client on purpose:
the project already has exactly one story for "shared, ephemeral, per-process
state or a real Redis behind it depending on ``REDIS_URL``" (see ``CACHES`` in
``config/settings/base.py``), and a second one here would be a second thing to
keep in sync with it. ``LocMemCache`` in dev and the test suite, a real Redis
in every container deployment — the pool does not know or care which.

**Pairing is atomic by construction, not by locking two keys.** At any moment
a category's pool holds *at most one* waiting player: the moment a second
player joins, they are paired with the first and both leave the pool in the
same critical section. So there is only ever one slot to protect, not a queue
to pop from — ``cache.add`` (an atomic "set only if absent", the one primitive
every Django cache backend implements the same way, Redis or not) is enough to
guard it, standing in for the Lua script/``BLMOVE`` primitive
``plan.md`` step 14 asks to name: **a single-slot compare-and-swap under a
short-lived mutex key**, below.

Two workers popping "simultaneously" therefore cannot hand the same opponent to
two matches: whichever acquires the mutex first sees the true state and clears
it; the other blocks out on the retry loop until the winner has released it,
then finds the slot empty and becomes the new waiter.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

from django.core.cache import cache

from apps.matches.constants import POOL_WAITING_TTL_SECONDS
from shared.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "Pairing",
    "PoolTimeout",
    "claim_for_bot",
    "join_pool",
    "leave_pool",
    "pool_size",
]

_LOCK_TIMEOUT_SECONDS = 5
_LOCK_RETRY_SECONDS = 0.02
_LOCK_MAX_WAIT_SECONDS = 2


class PoolTimeout(RuntimeError):
    """Could not acquire the pool's mutex within ``_LOCK_MAX_WAIT_SECONDS``.

    Raised rather than silently pairing wrong, or silently not pairing at all —
    a caller sees this exactly when the pool is under contention heavy enough
    that the cache backend itself is struggling, which is worth surfacing.
    """


@dataclass(frozen=True)
class Pairing:
    """The other player, when ``join_pool`` completes one."""

    opponent_id: str


def _waiting_key(*, category_slug: str) -> str:
    return f"matchmaking:waiting:{category_slug}"


def _lock_key(*, category_slug: str) -> str:
    return f"matchmaking:lock:{category_slug}"


def join_pool(*, category_slug: str, player_id: UUID | str) -> Pairing | None:
    """Add one player to a category's pool, pairing immediately if someone was
    already waiting there.

    Returns the opponent as a ``Pairing`` the instant a pairing exists —
    exactly one of the two callers racing to join gets one back, per the
    module docstring — or ``None`` if this player is now the one waiting.
    """
    player_id = str(player_id)
    with _mutex(category_slug=category_slug):
        waiting_key = _waiting_key(category_slug=category_slug)
        waiting = cache.get(waiting_key)
        if waiting is None:
            cache.set(waiting_key, player_id, timeout=POOL_WAITING_TTL_SECONDS)
            return None
        if waiting == player_id:
            # Same player retrying a join (e.g. a reconnect before any
            # opponent showed up) — refresh the TTL rather than pairing
            # someone against themselves.
            cache.set(waiting_key, player_id, timeout=POOL_WAITING_TTL_SECONDS)
            return None
        cache.delete(waiting_key)
        return Pairing(opponent_id=waiting)


def leave_pool(*, category_slug: str, player_id: UUID | str) -> None:
    """Withdraw one player, if and only if they are the one currently waiting.

    A no-op for a player who was never queued, or who has since been paired
    off by someone else — clearing the slot unconditionally could delete the
    *next* waiter's claim instead of this caller's own.
    """
    player_id = str(player_id)
    with _mutex(category_slug=category_slug):
        waiting_key = _waiting_key(category_slug=category_slug)
        if cache.get(waiting_key) == player_id:
            cache.delete(waiting_key)


def claim_for_bot(*, category_slug: str, player_id: UUID | str) -> bool:
    """Atomically withdraw ``player_id`` so ``apps.matches.bots`` may pair
    them against a CPU opponent instead of a human.

    Same mutex as ``join_pool``/``leave_pool``, and the same reason: the 15
    second wait (``FF_ENABLE_BOTS_IF_TIMEOUT``) and a human's own arrival race
    each other, so whichever caller actually holds the waiting slot when this
    runs must win outright rather than both firing. Returns ``False`` — a
    no-op, not an error — for a player who is no longer the one waiting: a
    human already claimed them (the ordinary, better outcome) or they left the
    pool on their own.
    """
    player_id = str(player_id)
    with _mutex(category_slug=category_slug):
        waiting_key = _waiting_key(category_slug=category_slug)
        if cache.get(waiting_key) != player_id:
            return False
        cache.delete(waiting_key)
        return True


def pool_size(*, category_slug: str) -> int:
    """0 or 1 — the pool never holds more, by construction. For tests and
    introspection, not a hot path."""
    return 0 if cache.get(_waiting_key(category_slug=category_slug)) is None else 1


class _mutex:
    """A short-lived, ``cache.add``-backed critical section around one
    category's waiting slot. Retries rather than blocking, since the cache
    backend offers nothing to block on."""

    def __init__(self, *, category_slug: str) -> None:
        self._key = _lock_key(category_slug=category_slug)
        self._acquired = False

    def __enter__(self) -> "_mutex":
        deadline = time.monotonic() + _LOCK_MAX_WAIT_SECONDS
        while not cache.add(self._key, "1", timeout=_LOCK_TIMEOUT_SECONDS):
            if time.monotonic() >= deadline:
                raise PoolTimeout(f"Could not acquire matchmaking lock {self._key!r}.")
            time.sleep(_LOCK_RETRY_SECONDS)
        self._acquired = True
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._acquired:
            cache.delete(self._key)
