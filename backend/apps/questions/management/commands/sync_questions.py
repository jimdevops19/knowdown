"""Load the categories and questions from ``apps/questions/resources/``.

Idempotent — upserts on ``slug``, so this is the way to *edit* a question:
change the YAML, re-run, and the row is corrected rather than duplicated.
Questions dropped from the YAML are deactivated, never deleted, because a
matchup that already played one points at that row.

    uv run python manage.py sync_questions
    uv run python manage.py sync_questions --dry-run
    uv run python manage.py sync_questions --category nba
    uv run python manage.py sync_questions --categories-only

(The command cannot be spelled ``sync-questions``: Django finds a command by
importing the module named after it, and a hyphen is not a legal module name.)
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core_common.exceptions import ValidationFailed
from apps.questions.services import sync


class Command(BaseCommand):
    help = "Load/refresh the question catalog from apps/questions/resources/."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report, then roll back without writing.",
        )
        parser.add_argument(
            "--categories-only",
            action="store_true",
            help="Load categories.yaml and stop.",
        )
        parser.add_argument(
            "--category",
            metavar="SLUG",
            help=(
                "Load only this category's folder. The sweep that deactivates "
                "dropped questions is narrowed with it, so other categories are "
                "left alone."
            ),
        )

    def handle(self, *args, **options) -> None:
        try:
            with transaction.atomic():
                categories = sync.sync_categories()
                self._report("categories", categories)

                if not options["categories_only"]:
                    questions = sync.sync_questions(category=options["category"])
                    self._report("questions", questions)

                if options["dry_run"]:
                    raise _Rollback
        except _Rollback:
            self.stdout.write(self.style.WARNING("dry run — rolled back"))
            return
        except ValidationFailed as exc:
            # The details are the point of a failed load: a reviewer fixing a
            # batch wants every problem at once, not the first one seven times.
            for problem in exc.details or []:
                self.stderr.write(f"  {problem}")
            raise CommandError(exc.message) from exc

        self.stdout.write(self.style.SUCCESS("Question resources loaded."))

    def _report(self, label: str, report: sync.LoadReport) -> None:
        self.stdout.write(f"{label + ':':12}{report}")
        for slug in report.deactivated:
            self.stdout.write(self.style.WARNING(f"  deactivated {slug}"))


class _Rollback(Exception):
    """Aborts the atomic block on ``--dry-run``; never escapes ``handle``."""
