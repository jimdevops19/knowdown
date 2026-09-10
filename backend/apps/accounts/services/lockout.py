"""Guessing gets slower, then stops.

The ``login`` throttle scope caps how *fast* one client may post to sign-in.
This is the other half — how many times one **address** may be wrong before the
door stops opening at all — and it exists because a rate limit alone does not
stop a password guess:

* a throttle counts per client IP, and an IP is either shared by everybody
  behind one gateway or changed at will by a script. The address someone is
  guessing at is the dimension that is always true;
* a rate is a speed limit, not a budget. 10/min forever is 14,400 guesses a
  day against one account, which is a word list.

The counters are keyed on **the address that was typed**, whether or not it
names an account. Asking whether it does would make the lockout itself an
account-existence oracle — exactly what ``LoginSerializer`` goes out of its way
to deny — and the typed string is hashed into the key, so listing the cache
does not hand over the list of who has been signing in.

Three responses, all decided by :func:`_block_seconds`:

1. the first few failures cost nothing — people mistype passwords;
2. past that, each further failure buys a **cooldown that doubles**, capped,
   served as a 429 with ``Retry-After`` and never as a ``sleep``: holding the
   request open would be a free way to pin every worker;
3. past the lockout threshold, a **temporary** lock. Temporary on purpose — a
   permanent one is a way to keep a rival out of their own account, so the
   attacker's reward for pushing on is that they wait.

A successful sign-in clears the counters, so the only person who meets this is
one who keeps being wrong.

**It fails open.** The counters live in the cache; a dead cache means no
lockout, the same trade the DRF throttles already make. Refusing every sign-in
when Redis blinks would turn a cache outage into a total outage.
"""

from __future__ import annotations

import hashlib
import math
import time

from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import Throttled

from shared.logging import get_logger

logger = get_logger(__name__)

#: One namespace for every key this module writes, so a stuck lock can be found
#: and dropped without knowing whose address it belongs to.
PREFIX = "login-guard"


class SignInLocked(Throttled):
    """A 429 that says how long the wait is in words a person reads.

    DRF's own ``Throttled`` renders it as "Expected available in 900 seconds",
    which is the wrong unit for a quarter of an hour and the wrong register for
    the one screen where somebody is already frustrated. The number still
    leaves as ``Retry-After`` (DRF's handler reads ``wait``), so a client can be
    exact even though the sentence is not.
    """

    def __init__(self, wait: int) -> None:
        self.wait = wait
        self.detail = (
            f"Too many sign-in attempts. Please try again in {_in_words(wait)}."
        )


def _in_words(seconds: int) -> str:
    if seconds < 60:
        return "a few seconds"
    minutes = round(seconds / 60)
    return "a minute" if minutes == 1 else f"{minutes} minutes"


def _digest(value: str) -> str:
    """Key material for an address, not the address itself."""
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _identity(email: str) -> str | None:
    """The account dimension: the address as typed, folded for case."""
    text = (email or "").strip().lower()
    return _digest(text) if text else None


def _dimensions(*, email: str, ip: str | None) -> list[tuple[str, str]]:
    """What one attempt is counted against: the address, and maybe the IP.

    The IP half is off by default (``LOGIN_LOCKOUT_BY_IP``). Behind an ingress
    that does not forward the real client address, every request shares one —
    so an IP lock there is a lock on the whole platform. It is the one switch
    in this module that can take the site down if it is turned on without
    checking what actually reaches Django.
    """
    dimensions: list[tuple[str, str]] = []
    identity = _identity(email)
    if identity:
        dimensions.append(("account", identity))
    if ip and settings.LOGIN_LOCKOUT_BY_IP:
        dimensions.append(("ip", _digest(ip)))
    return dimensions


def _block_seconds(failures: int) -> int:
    """How long the door stays shut after ``failures`` wrong answers."""
    if failures >= settings.LOGIN_LOCKOUT_AFTER:
        return settings.LOGIN_LOCKOUT_SECONDS
    if failures < settings.LOGIN_DELAY_AFTER:
        return 0
    delay = 2 ** (failures - settings.LOGIN_DELAY_AFTER)
    return min(delay, settings.LOGIN_DELAY_CAP_SECONDS)


def _blocked_for(kind: str, key: str) -> int:
    """Seconds still to wait on this key; 0 when it is not blocked."""
    until = cache.get(f"{PREFIX}:block:{kind}:{key}")
    if not until:
        return 0
    # Rounded *up*: nine tenths of a second is still a wait, and truncating it
    # to zero would report "not blocked" for most of the first — and shortest —
    # cooldown, the one that has to bite for the rest to ever be reached.
    return max(0, math.ceil(until - time.time()))


def _count_failure(kind: str, key: str) -> int:
    """Record one failure against a key and answer the running total.

    Read-modify-write rather than ``cache.incr``: incrementing a missing key
    raises, and TTL handling differs between backends. Two failures landing in
    the same instant can therefore count as one — an undercount of a single
    guess, on a counter that allows several, is not worth a lock for.
    """
    cache_key = f"{PREFIX}:fails:{kind}:{key}"
    failures = int(cache.get(cache_key) or 0) + 1
    cache.set(cache_key, failures, timeout=settings.LOGIN_FAILURE_WINDOW_SECONDS)
    return failures


def _clear(kind: str, key: str) -> None:
    cache.delete(f"{PREFIX}:fails:{kind}:{key}")
    cache.delete(f"{PREFIX}:block:{kind}:{key}")


def guard(*, email: str, ip: str | None = None) -> None:
    """Refuse a sign-in that is inside a cooldown or a lock.

    Called *before* the password is checked, so a locked address costs a
    guesser a 429 and no hash — and so the refusal cannot be told apart from
    one for an address that has no account at all.

    With ``LOGIN_LOCKOUT_ENFORCED`` off the failure is still counted and still
    logged; nobody is turned away. That is how the numbers become real before
    the limit starts refusing people.
    """
    for kind, key in _dimensions(email=email, ip=ip):
        wait = _blocked_for(kind, key)
        if not wait:
            continue
        logger.warning(
            "Sign-in refused — too many recent failures",
            auth_method="password",
            reason=f"{kind} is locked out",
            retry_after=wait,
        )
        if not settings.LOGIN_LOCKOUT_ENFORCED:
            continue
        raise SignInLocked(wait)


def record_failure(*, email: str, ip: str | None = None) -> None:
    """Count one wrong answer, and shut the door if there have been enough.

    The individual failure is logged by the view; what is logged here is the
    *pattern* — the line that says this is no longer somebody fumbling a
    password — with the running count on it, so a dashboard can alert on the
    shape rather than on single 401s, which are ordinary.
    """
    for kind, key in _dimensions(email=email, ip=ip):
        failures = _count_failure(kind, key)
        seconds = _block_seconds(failures)
        if seconds:
            cache.set(
                f"{PREFIX}:block:{kind}:{key}", time.time() + seconds, timeout=seconds
            )
        if failures < settings.LOGIN_DELAY_AFTER:
            continue
        locked = failures >= settings.LOGIN_LOCKOUT_AFTER
        logger.warning(
            "Sign-in locked out" if locked else "Repeated sign-in failures",
            auth_method="password",
            reason=f"{failures} failures against this {kind} in the window",
            count=failures,
            retry_after=seconds,
        )


def record_success(*, email: str, ip: str | None = None) -> None:
    """Forget the failures behind a sign-in that worked.

    Whoever is at the other end proved they hold a password, which is the
    evidence the counters were standing in for.
    """
    for kind, key in _dimensions(email=email, ip=ip):
        _clear(kind, key)
