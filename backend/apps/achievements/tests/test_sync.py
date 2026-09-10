"""``sync_achievements`` and the command over it — upserts on slug,
deactivates rather than deletes, refuses a bad file all at once."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from apps.achievements.models import Achievement
from apps.achievements.services import sync_achievements
from apps.achievements.services.sync import ACHIEVEMENTS_FILE
from apps.core_common.exceptions import ValidationFailed


class SyncAchievementsTests(TestCase):
    def test_loads_the_real_catalog(self):
        report = sync_achievements()
        self.assertEqual(len(report.created), 8)
        self.assertEqual(Achievement.objects.filter(is_active=True).count(), 8)

    def test_is_idempotent(self):
        sync_achievements()
        report = sync_achievements()
        self.assertEqual(report.created, [])
        self.assertEqual(len(report.updated), 8)

    def test_a_badge_dropped_from_the_file_is_deactivated_not_deleted(self, tmp_path=None):
        sync_achievements()
        extra = Achievement.objects.create(
            slug="retired-badge", name="Retired", description="No longer in the file."
        )
        sync_achievements()  # the real file, which does not mention it
        extra.refresh_from_db()
        self.assertFalse(extra.is_active)
        self.assertTrue(Achievement.all_objects.filter(pk=extra.pk).exists())

    def test_refuses_a_file_with_duplicate_slugs(self):
        raw = (
            "- slug: dup\n  name: Dup\n  description: one\n"
            "- slug: dup\n  name: Dup Again\n  description: two\n"
        )
        path = Path(self._make_temp_yaml(raw))
        with self.assertRaises(ValidationFailed):
            sync_achievements(path=path)

    def test_refuses_an_unknown_key(self):
        raw = "- slug: bad\n  name: Bad\n  description: x\n  points: 10\n"
        path = Path(self._make_temp_yaml(raw))
        with self.assertRaises(ValidationFailed):
            sync_achievements(path=path)

    def _make_temp_yaml(self, raw: str) -> str:
        path = ACHIEVEMENTS_FILE.parent / "_test_tmp.yaml"
        path.write_text(raw, encoding="utf-8")
        self.addCleanup(path.unlink)
        return str(path)


class SyncAchievementsCommandTests(TestCase):
    def test_dry_run_writes_nothing(self):
        out = StringIO()
        call_command("sync_achievements", "--dry-run", stdout=out)
        self.assertIn("Would sync", out.getvalue())
        self.assertEqual(Achievement.objects.count(), 0)

    def test_writes_the_catalog(self):
        out = StringIO()
        call_command("sync_achievements", stdout=out)
        self.assertIn("Achievements synced", out.getvalue())
        self.assertEqual(Achievement.objects.filter(is_active=True).count(), 8)
