"""Abuse limits on the two things a live match costs the platform: answering a
question, and asking to be matched — plus a cap on how many sockets one
account may hold open at once.

This is the WebSocket half of the family ``apps.accounts.services.lockout``
started: guessing gets slower, then stops. The reasoning is the same, and so
is the shape (count first, refuse second, fail open) — but the mechanism
cannot be DRF's ``ScopedRateThrottle``, because there is no request/response
cycle here for a throttle class to hang a scope off. ``apps.matches.pool``
already solved "one atomic counter, shared across every process, backed by
whatever ``CACHES['default']`` is" for pairing; this reuses that primitive for
counting instead of mutual exclusion.

Three limits, all keyed on the **player id** — never the socket, which a
client can always open a fresh one of:

* ``check_answer_submit_rate`` — how many ``events.ANSWER_SUBMIT`` frames one
  player may send per window. A legitimate client sends at most one per
  question; a client retrying a malformed payload in a loop, or scripting
  ``submit_answer`` to probe ``evaluate_answer``'s error messages, sends many.
* ``check_matchmaking_join_rate`` — how many times one player may join a
  category's pool per window. Joining and leaving is the one action a client
  can repeat for free (unlike answering, it costs no question), which makes it
  the cheapest way to hammer ``apps.matches.pool``'s ``cache.add`` mutex.
* ``register_socket`` / ``unregister_socket`` — how many sockets (matchmaking
  *and* matchup, added together — nothing here cares which) one player may
  hold open at once. A budget, not a rate: opening ten tabs costs the pool and
  the channel layer ten times the group membership and presence traffic of
  one, whether or not any of them ever sends a frame.

**Counting before enforcing.** ``settings.MATCH_ABUSE_LIMITS_ENFORCED`` off —
the default in ``config.settings.test`` — still counts and logs every hit,
just never raises. That is how the numbers become real before a limit starts
turning players away, the same trade ``LOGIN_LOCKOUT_ENFORCED`` makes.

**It fails open.** Every counter lives in the cache; a dead cache means no
limit, not a refused connection — the same trade the DRF throttles and
``apps.accounts.services.lockout`` already make, and for the same reason:
degrading the live view is one thing, 500ing (or here, closing) every socket
because Redis blinked is a worse outage than the one being guarded against.
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

from shared.logging import get_logger

logger = get_logger(__name__)

#: One namespace for every key this module writes, so a stuck counter can be
#: found and dropped without knowing which player it belongs to.
PREFIX = "match-abuse"


class RateLimited(Exception):
    """A caller has exceeded one of this module's limits and enforcement is
    on. Consumers catch this beside ``core_common.exceptions.DomainError`` and
    report it the same way — a slowdown, not a reason to end the game."""

    def __init__(self, *, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limited; retry after {retry_after}s")


def _increment(kind: str, key: str, *, window_seconds: int) -> int:
    """Count one hit against ``kind:key`` inside a rolling window.

    ``cache.incr`` raises ``ValueError`` on a missing key rather than
    creating one — unlike Redis' own ``INCR`` — so the first hit in a window
    is a plain ``set``. Two first-hits landing in the same instant can
    therefore both count as 1 instead of 1-then-2, which under-counts a
    single race by one; not worth a lock, in a limit sized in the tens.
    """
    cache_key = f"{PREFIX}:{kind}:{key}"
    try:
        return cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=window_seconds)
        return 1


def _check_rate(*, kind: str, key: str, limit: int, window_seconds: int, event: str) -> None:
    count = _increment(kind, str(key), window_seconds=window_seconds)
    if count <= limit:
        return
    logger.warning(
        f"{event} rate exceeded",
        caller="user",
        reason=f"{count} in the last {window_seconds}s (limit {limit})",
        count=count,
        retry_after=window_seconds,
    )
    if settings.MATCH_ABUSE_LIMITS_ENFORCED:
        raise RateLimited(retry_after=window_seconds)


def check_answer_submit_rate(*, player_id) -> None:
    """Refuse (once enforced) a player sending more than
    ``ANSWER_SUBMIT_RATE_LIMIT`` answer frames per
    ``ANSWER_SUBMIT_RATE_WINDOW_SECONDS`` — called before the payload ever
    reaches ``apps.matches.services.submit_answer``, so a burst costs no
    evaluation and no query."""
    _check_rate(
        kind="answer",
        key=player_id,
        limit=settings.ANSWER_SUBMIT_RATE_LIMIT,
        window_seconds=settings.ANSWER_SUBMIT_RATE_WINDOW_SECONDS,
        event="Answer submission",
    )


def check_matchmaking_join_rate(*, player_id) -> None:
    """Refuse (once enforced) a player joining a matchmaking pool more than
    ``MATCHMAKING_JOIN_RATE_LIMIT`` times per
    ``MATCHMAKING_JOIN_RATE_WINDOW_SECONDS`` — checked in ``connect``, before
    ``apps.matches.pool.join_pool`` ever touches the mutex."""
    _check_rate(
        kind="join",
        key=player_id,
        limit=settings.MATCHMAKING_JOIN_RATE_LIMIT,
        window_seconds=settings.MATCHMAKING_JOIN_RATE_WINDOW_SECONDS,
        event="Matchmaking join",
    )


def _socket_count_key(player_id) -> str:
    return f"{PREFIX}:sockets:{player_id}"


def register_socket(*, player_id) -> None:
    """Count one more open socket for this player, raising (once enforced) if
    that puts them over ``MAX_CONCURRENT_SOCKETS_PER_PLAYER``.

    Call once a socket has authenticated, before it does anything the budget
    is meant to guard. On refusal the count is immediately given back
    (``unregister_socket``) — this connection is about to be closed, not
    opened, so it must not occupy a slot nobody will ever release.

    The TTL is a safety net, the same role ``apps.matches.presence``'s TTL
    plays: a process that dies between ``register_socket`` and the
    ``disconnect`` that would call ``unregister_socket`` must not strand a
    slot forever. It is refreshed on every register so a long-lived socket's
    slot does not expire out from under it.
    """
    key = _socket_count_key(player_id)
    try:
        count = cache.incr(key)
        cache.touch(key, settings.CONCURRENT_SOCKET_TTL_SECONDS)
    except ValueError:
        cache.set(key, 1, timeout=settings.CONCURRENT_SOCKET_TTL_SECONDS)
        count = 1
    if count <= settings.MAX_CONCURRENT_SOCKETS_PER_PLAYER:
        return
    logger.warning(
        "Too many concurrent sockets for one account",
        caller="user",
        reason=f"{count} open (limit {settings.MAX_CONCURRENT_SOCKETS_PER_PLAYER})",
        count=count,
    )
    if settings.MATCH_ABUSE_LIMITS_ENFORCED:
        unregister_socket(player_id=player_id)
        raise RateLimited(retry_after=5)


def unregister_socket(*, player_id) -> None:
    """Give back one socket slot. Safe to call more than once for the same
    player — a count that is already at zero is left there, never negative,
    since a negative budget would just mean one extra socket is allowed next
    time."""
    key = _socket_count_key(player_id)
    try:
        if cache.decr(key) < 0:
            cache.set(key, 0, timeout=settings.CONCURRENT_SOCKET_TTL_SECONDS)
    except ValueError:
        pass
