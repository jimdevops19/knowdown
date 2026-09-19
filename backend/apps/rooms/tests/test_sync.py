"""``sync_rooms`` and the command over it — upserts on slug, deactivates
rather than deletes, refuses a bad file all at once."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.core_common.exceptions import ValidationFailed
from apps.questions.tests.factories import make_category
from apps.rooms.models import Room, RoomCategory
from apps.rooms.services import sync_rooms
from apps.rooms.services.sync import ROOMS_FILE

ONE_ROOM = """
- name: Finals
  slug: finals-room
  questions_asked_ranges: [4, 5, 6]
  categories:
    - slug: nba
      filter_tags:
        topic: finals
"""


class SyncRoomsTests(TestCase):
    def setUp(self):
        self.category = make_category()

    def _write(self, raw: str) -> Path:
        path = ROOMS_FILE.parent / "_test_tmp.yaml"
        path.write_text(raw, encoding="utf-8")
        self.addCleanup(lambda: path.exists() and path.unlink())
        return path

    def test_loads_the_shipped_lobby(self):
        """The real file must load — it is what a deploy runs."""
        report = sync_rooms()
        self.assertTrue(report.created)
        self.assertEqual(Room.objects.filter(is_active=True).count(), len(report.created))

    def test_loads_a_room_with_its_categories(self):
        sync_rooms(path=self._write(ONE_ROOM))
        room = Room.objects.get(slug="finals-room")
        self.assertEqual(room.name, "Finals")
        self.assertEqual(room.question_count_choices, [4, 5, 6])
        entry = room.categories.get()
        self.assertEqual(entry.category, self.category)
        self.assertEqual(entry.filter_tags, {"topic": "finals"})
        self.assertEqual(entry.order, 1)

    def test_is_idempotent(self):
        path = self._write(ONE_ROOM)
        sync_rooms(path=path)
        report = sync_rooms(path=path)
        self.assertEqual(report.created, [])
        self.assertEqual(report.updated, ["finals-room"])
        self.assertEqual(RoomCategory.objects.count(), 1)

    def test_editing_a_room_corrects_the_row_rather_than_adding_one(self):
        path = self._write(ONE_ROOM)
        sync_rooms(path=path)
        sync_rooms(
            path=self._write(
                ONE_ROOM.replace("questions_asked_ranges: [4, 5, 6]", "questions_asked_ranges: [7]")
            )
        )
        self.assertEqual(Room.objects.count(), 1)
        self.assertEqual(Room.objects.get().question_count_choices, [7])

    def test_categories_are_replaced_not_merged(self):
        """A category dropped from a room's list must leave the room."""
        other = make_category(slug="f1", name="F1")
        sync_rooms(
            path=self._write(
                ONE_ROOM + "    - slug: f1\n"
            )
        )
        self.assertEqual(Room.objects.get().categories.count(), 2)
        sync_rooms(path=self._write(ONE_ROOM))
        self.assertEqual(
            list(Room.objects.get().categories.values_list("category__slug", flat=True)),
            ["nba"],
        )
        # The category itself is untouched — only the room's link to it goes.
        self.assertTrue(type(other).objects.filter(pk=other.pk).exists())

    def test_a_room_dropped_from_the_file_is_deactivated_not_deleted(self):
        sync_rooms(path=self._write(ONE_ROOM))
        room = Room.objects.get(slug="finals-room")
        sync_rooms(path=self._write("[]"))
        room.refresh_from_db()
        self.assertFalse(room.is_active)
        self.assertTrue(Room.all_objects.filter(pk=room.pk).exists())

    def test_a_room_back_in_the_file_is_revived_not_duplicated(self):
        sync_rooms(path=self._write(ONE_ROOM))
        Room.objects.get(slug="finals-room").delete()  # soft delete
        sync_rooms(path=self._write(ONE_ROOM))
        self.assertEqual(Room.all_objects.filter(slug="finals-room").count(), 1)
        self.assertIsNone(Room.objects.get(slug="finals-room").deleted_at)

    def test_refuses_an_unknown_category(self):
        with self.assertRaises(ValidationFailed) as caught:
            sync_rooms(path=self._write(ONE_ROOM.replace("slug: nba", "slug: cricket")))
        self.assertIn("cricket", caught.exception.message)

    def test_refuses_duplicate_room_slugs(self):
        with self.assertRaises(ValidationFailed):
            sync_rooms(path=self._write(ONE_ROOM + ONE_ROOM))

    def test_refuses_a_room_listing_a_category_twice(self):
        with self.assertRaises(ValidationFailed):
            sync_rooms(path=self._write(ONE_ROOM + "    - slug: nba\n"))

    def test_refuses_an_unknown_key(self):
        with self.assertRaises(ValidationFailed):
            sync_rooms(path=self._write(ONE_ROOM + "  difficulty: hard\n"))

    def test_refuses_a_room_with_no_categories(self):
        raw = "- name: Empty\n  slug: empty\n  questions_asked_ranges: [3]\n  categories: []\n"
        with self.assertRaises(ValidationFailed):
            sync_rooms(path=self._write(raw))

    def test_refuses_an_out_of_range_question_count(self):
        with self.assertRaises(ValidationFailed):
            sync_rooms(path=self._write(ONE_ROOM.replace("[4, 5, 6]", "[0]")))
        with self.assertRaises(ValidationFailed):
            sync_rooms(path=self._write(ONE_ROOM.replace("[4, 5, 6]", "[200]")))

    def test_refuses_a_repeated_question_count(self):
        """A repeated count is a silent weighting nobody authored."""
        with self.assertRaises(ValidationFailed):
            sync_rooms(path=self._write(ONE_ROOM.replace("[4, 5, 6]", "[5, 5, 6]")))

    def test_question_counts_are_stored_ascending(self):
        sync_rooms(path=self._write(ONE_ROOM.replace("[4, 5, 6]", "[6, 4, 5]")))
        self.assertEqual(Room.objects.get().question_count_choices, [4, 5, 6])

    def test_refuses_a_tag_key_that_would_address_an_array_index(self):
        """``2000s:`` as a *key* can never match — refused where it is fixable."""
        with self.assertRaises(ValidationFailed):
            sync_rooms(path=self._write(ONE_ROOM.replace("topic: finals", "2000s: yes")))

    def test_unquoted_yaml_scalars_become_the_strings_tags_actually_hold(self):
        """``era: 2000`` is an int to YAML and would match no question at all."""
        sync_rooms(path=self._write(ONE_ROOM.replace("topic: finals", "era: 2000")))
        self.assertEqual(Room.objects.get().categories.get().filter_tags, {"era": "2000"})

    def test_a_room_may_name_an_inactive_category(self):
        """Out of season is not a reason to fail the whole file."""
        self.category.is_active = False
        self.category.save(update_fields=["is_active"])
        sync_rooms(path=self._write(ONE_ROOM))
        self.assertTrue(Room.objects.filter(slug="finals-room").exists())


class SyncRoomsCommandTests(TestCase):
    def setUp(self):
        make_category()

    def test_the_command_loads_the_shipped_lobby(self):
        out = StringIO()
        call_command("sync_rooms", stdout=out)
        self.assertIn("Rooms synced", out.getvalue())
        self.assertTrue(Room.objects.exists())

    def test_dry_run_writes_nothing(self):
        out = StringIO()
        call_command("sync_rooms", "--dry-run", stdout=out)
        self.assertIn("dry run", out.getvalue())
        self.assertFalse(Room.objects.exists())

    def test_a_bad_file_fails_the_command_and_prints_every_problem(self):
        """A refused load exits non-zero *and* names what to fix — the whole
        point of collecting problems rather than raising at the first."""
        errors = StringIO()
        with patch(
            "apps.rooms.management.commands.sync_rooms.sync_rooms",
            side_effect=ValidationFailed("Invalid rooms.", details=["one", "two"]),
        ):
            with self.assertRaises(CommandError):
                call_command("sync_rooms", stdout=StringIO(), stderr=errors)
        self.assertIn("one", errors.getvalue())
        self.assertIn("two", errors.getvalue())
