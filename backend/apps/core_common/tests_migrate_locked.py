"""``migrate_locked`` on SQLite — the only branch the test database exercises.

The Postgres advisory-lock path (the reason this command exists) needs a real
Postgres connection to prove serialisation under; that is deployment-shaped,
not unit-test-shaped. What a test *can* prove on SQLite is the fallback this
command must not break: no advisory lock support, so it degrades to a plain
``migrate`` rather than raising.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class MigrateLockedOnSqliteTests(TestCase):
    def test_it_degrades_to_a_plain_migrate(self) -> None:
        out = StringIO()
        call_command("migrate_locked", stdout=out)
        self.assertIn("no advisory lock", out.getvalue())
