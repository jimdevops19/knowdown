"""Fill in the ladder rows the lazy seeding hook can't reach.

``services.ensure_ranking`` only fires when a matchup needs a rating that is
not there yet, which leaves every player who predates a category — or predates
the hook itself — with no row until their first matchup in it settles. This
command closes that gap, so a ladder read (``selectors.ladder``) really does
list every player who could play in it.

    uv run python manage.py backfill_rankings
    uv run python manage.py backfill_rankings --category nba
    uv run python manage.py backfill_rankings --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.categories.models import Category
from apps.rankings import selectors, services


class Command(BaseCommand):
    help = "Seed a Ranking row, at the default rating, for every player missing one in a category."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--category",
            metavar="SLUG",
            help="Restrict to one category. Defaults to every active category.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Also backfill categories that are switched off.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many rows would be created without writing any.",
        )

    def handle(self, *args, **options) -> None:
        categories = self._categories(options)
        if not categories:
            raise CommandError("No categories to backfill.")

        for category in categories:
            if options["dry_run"]:
                missing = selectors.unrated_players(category=category).count()
                self.stdout.write(
                    f"{category.slug}: {missing} player(s) would be seeded."
                )
                continue
            created = services.seed_all_players(category=category)
            self.stdout.write(
                self.style.SUCCESS(f"{category.slug}: seeded {created} player(s).")
            )

    def _categories(self, options) -> list[Category]:
        if options["category"]:
            category = Category.objects.filter(slug=options["category"]).first()
            if category is None:
                raise CommandError(f"No category with slug '{options['category']}'.")
            return [category]
        queryset = Category.objects.all()
        if not options["include_inactive"]:
            queryset = queryset.filter(is_active=True)
        return list(queryset)
