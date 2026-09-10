"""Guessing gets slower, then stops — and does it without holding a worker.

Enforcement is off in the test settings (see ``config/settings/test.py``), so
these ask for it back with ``@override_settings`` and clear the cache
themselves. Both halves matter: the counters outlive a test method, and a
neighbouring test that signs in wrong on purpose must not inherit a lock.
"""

from __future__ import annotations

import time

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.services import lockout

from .factories import PASSWORD, make_user

ENFORCED = override_settings(
    LOGIN_LOCKOUT_ENFORCED=True,
    LOGIN_DELAY_AFTER=3,
    LOGIN_LOCKOUT_AFTER=5,
    LOGIN_LOCKOUT_SECONDS=900,
    LOGIN_LOCKOUT_BY_IP=False,
)


@ENFORCED
class LockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        make_user(email="veteran@example.com")

    def _wrong(self, email="veteran@example.com"):
        return self.client.post(
            "/api/v1/auth/token/", {"email": email, "password": "wrong-one-99"}, format="json"
        )

    def test_the_first_few_mistakes_cost_nothing(self):
        """People mistype passwords; punishing that is a support queue."""
        for _ in range(3):
            self.assertEqual(self._wrong().status_code, 401)

    def test_past_that_the_door_shuts_for_a_while(self):
        for _ in range(3):
            self._wrong()
        refused = self._wrong()
        self.assertEqual(refused.status_code, 429)
        self.assertIn("Retry-After", refused)

    def test_the_wait_is_a_header_and_not_a_held_request(self):
        """A delay implemented as `sleep` would be a free way to pin every
        worker in the pool — the wrong end of the trade."""
        for _ in range(4):
            self._wrong()
        started = time.monotonic()
        refused = self._wrong()
        self.assertEqual(refused.status_code, 429)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertGreater(int(refused["Retry-After"]), 0)

    def test_enough_failures_become_a_lock(self):
        """The guesses are counted through the service, not the endpoint: the
        endpoint refuses a caller who is inside a cooldown *before* it counts
        anything, which is the point of the cooldown — reaching the lock takes
        someone who waits each one out."""
        for _ in range(6):
            lockout.record_failure(email="veteran@example.com")
        refused = self._wrong()
        self.assertEqual(refused.status_code, 429)
        self.assertGreaterEqual(int(refused["Retry-After"]), 60)

    def test_the_lock_is_temporary(self):
        """A permanent one would be a way to keep a rival out of their own
        account by guessing at it."""
        for _ in range(6):
            lockout.record_failure(email="veteran@example.com")
        self.assertLessEqual(int(self._wrong()["Retry-After"]), 900)

    def test_a_cooldown_costs_a_guesser_its_own_wait(self):
        """Being refused does not count as a guess, so a script hammering the
        endpoint gets no further than the cooldown it is already inside."""
        for _ in range(4):
            self._wrong()
        first = int(self._wrong()["Retry-After"])
        for _ in range(5):
            self._wrong()
        self.assertLessEqual(int(self._wrong()["Retry-After"]), first)

    def test_an_address_with_no_account_locks_too(self):
        """Counted per address *typed*, never per account found — asking
        whether it exists would rebuild the oracle sign-in refuses to be."""
        for _ in range(4):
            self._wrong(email="nobody@example.com")
        self.assertEqual(self._wrong(email="nobody@example.com").status_code, 429)

    def test_signing_in_clears_the_count(self):
        for _ in range(2):
            self._wrong()
        ok = self.client.post(
            "/api/v1/auth/token/",
            {"email": "veteran@example.com", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(ok.status_code, 200)
        for _ in range(3):
            self.assertEqual(self._wrong().status_code, 401)

    def test_one_address_locked_does_not_lock_another(self):
        for _ in range(5):
            self._wrong(email="nobody@example.com")
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/token/",
                {"email": "veteran@example.com", "password": PASSWORD},
                format="json",
            ).status_code,
            200,
        )


class CountingWithoutEnforcingTests(TestCase):
    """With enforcement off the failures are still counted and logged — which
    is how the numbers are real on the day the limit is switched on."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        make_user(email="veteran@example.com")

    def test_nobody_is_turned_away(self):
        for _ in range(8):
            response = self.client.post(
                "/api/v1/auth/token/",
                {"email": "veteran@example.com", "password": "wrong-one-99"},
                format="json",
            )
            self.assertEqual(response.status_code, 401)

    def test_but_the_counter_moved(self):
        for _ in range(8):
            lockout.record_failure(email="veteran@example.com")
        self.assertGreater(
            lockout._blocked_for("account", lockout._identity("veteran@example.com")), 0
        )


class CacheKeyTests(TestCase):
    def test_an_address_is_hashed_into_the_key(self):
        """A cache key is readable to anyone who can list Redis; dumping the
        keys must not hand over the list of who has been signing in."""
        key = lockout._identity("Veteran@Example.com")
        self.assertNotIn("veteran", key)
        self.assertEqual(key, lockout._identity("veteran@example.com"))
