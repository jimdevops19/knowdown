"""Load ``resources/achievements.yaml`` into the ``Achievement`` table.

    uv run python manage.py sync_achievements
    uv run python manage.py sync_achievements --dry-run

The authoring loop this exists for: edit the YAML, review it, run this.
Idempotent — upserts on ``slug`` — the same loop ``sync_questions`` gives the
question catalog.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.achievements.services import sync_achievements


class Command(BaseCommand):
    help = "Load apps/achievements/resources/achievements.yaml into the Achievement table."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report what would change, writing nothing.",
        )

    def handle(self, *args, **options) -> None:
        if options["dry_run"]:
            with transaction.atomic():
                report = sync_achievements()
                transaction.set_rollback(True)
            self.stdout.write(f"Would sync: {report}")
            return

        report = sync_achievements()
        self.stdout.write(self.style.SUCCESS(f"Achievements synced: {report}"))
