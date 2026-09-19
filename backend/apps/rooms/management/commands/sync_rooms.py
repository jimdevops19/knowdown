"""Load ``apps/rooms/resources/rooms.yaml`` into the ``Room`` tables.

    uv run python manage.py sync_rooms
    uv run python manage.py sync_rooms --dry-run

Idempotent — upserts on ``slug`` — so this is the way to *edit* a room: change
the YAML, re-run, and the row is corrected rather than duplicated. Rooms
dropped from the file are deactivated, never deleted, because a matchup already
played in one points at that row.

Run it **after** ``sync_questions``: a room names the categories it draws from,
and a category with no row behind it fails the load rather than being invented.

(The command cannot be spelled ``sync-rooms``: Django finds a command by
importing the module named after it, and a hyphen is not a legal module name.)
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core_common.exceptions import ValidationFailed
from apps.rooms.services import sync_rooms


class Command(BaseCommand):
    help = "Load apps/rooms/resources/rooms.yaml into the Room tables."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report what would change, writing nothing.",
        )

    def handle(self, *args, **options) -> None:
        try:
            with transaction.atomic():
                report = sync_rooms()
                if options["dry_run"]:
                    transaction.set_rollback(True)
        except ValidationFailed as exc:
            # The details are the point of a failed load: somebody fixing a
            # batch wants every problem at once, not the first one seven times.
            for problem in exc.details or []:
                self.stderr.write(f"  {problem}")
            raise CommandError(exc.message) from exc

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"dry run — would sync: {report}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Rooms synced: {report}"))
        for slug in report.deactivated:
            self.stdout.write(self.style.WARNING(f"  deactivated {slug}"))
