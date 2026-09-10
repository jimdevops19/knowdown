"""``migrate``, serialised across every process that might be starting at once.

Django does not lock the migration table. Two API replicas rolling out
together both read ``django_migrations``, both decide the same migration is
unapplied, and both run it — which on Postgres ends as a deadlock on the
system catalogs, a duplicate-column error, or (worst) a half-applied migration
whose row was never written, because DDL that is transactional still races
when two transactions are doing it.

The usual answer is "only ever run migrate from one place". That is a
*process* control, and it fails the moment the platform restarts a replica: an
entrypoint runs per replica, so with more than one there is more than one of
them, started together, by design. So the exclusion is taken in the one place
both of them can see — a Postgres advisory lock, held for the length of the
migrate.

The second replica does not fail and does not skip: it *waits*, then runs
migrate itself and finds there is nothing left to do (a few hundred
milliseconds), which is exactly the behaviour that makes this safe to run from
every replica's entrypoint rather than from one designated place.

On SQLite there is no advisory lock and no concurrency to speak of, so this
degrades to a plain migrate.
"""

from __future__ import annotations

import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

# Arbitrary but fixed: any process using this key excludes any other. Chosen
# once and never changed — a different key is a different lock, which would
# quietly restore the race this command exists to remove.
LOCK_KEY = 4_912_337_100


class Command(BaseCommand):
    help = "Run migrate while holding a database-wide advisory lock."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--timeout", type=int, default=600,
            help="Seconds to wait for the lock before giving up (default: "
            "%(default)s). Giving up is a failure: the process restarts and "
            "tries again, which is preferable to booting on an unmigrated "
            "schema.",
        )
        parser.add_argument(
            "--database", default="default", help="Connection alias to migrate."
        )

    def handle(self, *args, **options) -> None:
        connection = connections[options["database"]]

        if connection.vendor != "postgresql":
            self.stdout.write(f"{connection.vendor}: no advisory lock, migrating directly.")
            call_command("migrate", "--noinput", database=options["database"])
            return

        self._acquire(connection=connection, timeout=options["timeout"])
        try:
            call_command("migrate", "--noinput", database=options["database"])
        finally:
            self._release(connection=connection)

    def _acquire(self, *, connection, timeout: int) -> None:
        deadline = time.monotonic() + timeout
        waited = False
        while True:
            with connection.cursor() as cursor:
                # try_ rather than pg_advisory_lock: blocking in the database
                # would hold the connection open with nothing to show for it,
                # and there would be no way to report *why* the process is stuck.
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_KEY])
                if cursor.fetchone()[0]:
                    if waited:
                        self.stdout.write("Lock acquired.")
                    return
            if time.monotonic() >= deadline:
                raise CommandError(
                    f"Timed out after {timeout}s waiting for the migration lock. "
                    "Another process is still migrating, or one died holding the "
                    "lock — check for a stuck connection with: SELECT * FROM "
                    f"pg_locks WHERE objid = {LOCK_KEY % 2**32};"
                )
            if not waited:
                self.stdout.write("Another process is migrating; waiting for the lock…")
                waited = True
            time.sleep(1)

    def _release(self, *, connection) -> None:
        # Session-scoped, so a crashed process releases it when its connection
        # drops — the lock cannot outlive the thing it was protecting.
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
        except Exception as exc:  # noqa: BLE001 — never mask a migrate failure
            self.stderr.write(
                f"Could not release the migration lock ({exc}); it will drop "
                "with the connection."
            )
