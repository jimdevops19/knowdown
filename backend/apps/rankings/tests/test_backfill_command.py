"""``manage.py backfill_rankings`` — the ladder rows the lazy seeding hook
can't reach: players (and categories) that predate it."""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.categories.models import Category
from apps.matches.constants import DEFAULT_PLAYER_RATING
from apps.matches.tests.factories import stock_category
from apps.players.tests.factories import make_player
from apps.questions.tests.factories import make_category
from apps.rankings.models import Ranking


def run_command(*args) -> tuple[str, str]:
    out, err = StringIO(), StringIO()
    call_command("backfill_rankings", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


class BackfillRankingsTests(TestCase):
    def setUp(self) -> None:
        self.category = stock_category(count=1)
        self.player_one = make_player(email="one@example.com")
        self.player_two = make_player(email="two@example.com")

    def test_seeds_every_player_missing_a_row(self):
        out, _ = run_command("--category", self.category.slug)
        self.assertIn("seeded 2 player(s)", out)
        self.assertEqual(Ranking.objects.filter(category=self.category).count(), 2)
        for player in (self.player_one, self.player_two):
            entry = Ranking.objects.get(player=player, category=self.category)
            self.assertEqual(entry.rating, DEFAULT_PLAYER_RATING)

    def test_is_idempotent(self):
        run_command("--category", self.category.slug)
        out, _ = run_command("--category", self.category.slug)
        self.assertIn("seeded 0 player(s)", out)
        self.assertEqual(Ranking.objects.filter(category=self.category).count(), 2)

    def test_dry_run_writes_nothing(self):
        out, _ = run_command("--category", self.category.slug, "--dry-run")
        self.assertIn("2 player(s) would be seeded", out)
        self.assertEqual(Ranking.objects.count(), 0)

    def test_unknown_category_is_a_command_error(self):
        with self.assertRaises(CommandError):
            run_command("--category", "does-not-exist")

    def test_defaults_to_every_active_category(self):
        inactive = stock_category(category=make_category(slug="f1", name="F1"), count=1)
        Category.objects.filter(pk=inactive.pk).update(is_active=False)

        run_command()

        self.assertEqual(Ranking.objects.filter(category=self.category).count(), 2)
        self.assertFalse(Ranking.objects.filter(category=inactive).exists())

    def test_include_inactive_reaches_a_switched_off_category(self):
        inactive = stock_category(category=make_category(slug="f1", name="F1"), count=1)
        Category.objects.filter(pk=inactive.pk).update(is_active=False)
        inactive.refresh_from_db()

        run_command("--include-inactive")

        self.assertEqual(Ranking.objects.filter(category=inactive).count(), 2)
