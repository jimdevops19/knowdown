"""Editing the resource files from outside a text editor.

The subject here is the *pair* of effects, and every test is about them not
coming apart: an edit writes YAML and then loads it, a refused edit writes
neither, and what lands in the file is text a person would have been willing to
type. A create that only inserted a row would pass a test that asserted on the
database — so none of these assert only on the database.

The tree is temporary, as it is in ``test_sync``: the real catalog is content
that changes every week, and these tests *write* to what they point at.
"""

from __future__ import annotations

import yaml

from apps.core_common.exceptions import ValidationFailed
from apps.questions.models import (
    OrderingQuestion,
    SingleAnswerQuestion,
    TrueFalseQuestion,
)
from apps.questions.services import authoring
from apps.questions.tests.test_sync import ResourceTreeTestCase, single_answer

#: A file header with a comment in it, so the surgical-edit tests have something
#: that would be lost by a dumb round trip through a YAML dumper.
COMMENTED_FILE = """\
# NBA — single-answer questions.
#
# Every question here has exactly one right option.

category: nba

time_limit_seconds: 10

questions:
  # The oldest one in the file.
  - type: single-answer
    slug: who-scored
    description: Who won it?
    level: 3
    tags: {topic: teams}
    options:
      - text: Boston Celtics
        is_correct: true
      - text: Los Angeles Lakers

  # A second one, to have something after the first.
  - type: single-answer
    slug: who-else
    description: Who else?
    level: 4
    options:
      - text: Chicago Bulls
        is_correct: true
      - text: Detroit Pistons
"""


class AuthoringTestCase(ResourceTreeTestCase):
    """A category folder with one commented file in it, already loaded."""

    def setUp(self) -> None:
        super().setUp()
        self.folder = self.root / "nba"
        self.folder.mkdir(exist_ok=True)
        self.path = self.folder / "single-answer.yaml"
        self.path.write_text(COMMENTED_FILE, encoding="utf-8")
        self.load()

    def entries(self, path=None) -> list[dict]:
        document = yaml.safe_load((path or self.path).read_text(encoding="utf-8"))
        return document["questions"]

    def slugs(self, path=None) -> list[str]:
        return [entry["slug"] for entry in self.entries(path)]


class CreateTests(AuthoringTestCase):
    def test_a_new_question_is_appended_to_the_file_and_loaded(self):
        result = authoring.save_entry(
            category="nba", entry=single_answer("a-new-one", level=6)
        )

        self.assertEqual(result.action, "created")
        self.assertEqual(self.slugs(), ["who-scored", "who-else", "a-new-one"])
        self.assertEqual(result.report.created, ["a-new-one"])
        question = SingleAnswerQuestion.objects.get(slug="a-new-one")
        self.assertEqual(question.level, 6)
        self.assertEqual(question.options.count(), 2)

    def test_the_new_block_reads_like_a_hand_written_one(self):
        authoring.save_entry(
            category="nba",
            entry=single_answer("a-new-one", tags={"topic": "teams", "era": "90s"}),
        )
        text = self.path.read_text(encoding="utf-8")

        # The keys in the order a reader expects them, the tags inline the way
        # every shipped file writes them, and the nested list indented under
        # the key that owns it.
        self.assertIn("  - type: single-answer\n    slug: a-new-one\n", text)
        self.assertIn("    tags: {topic: teams, era: 90s}\n", text)
        self.assertIn("    options:\n      - text: Boston Celtics\n", text)
        # `is_active: true` is what every other entry says by saying nothing.
        self.assertNotIn("is_active", text)

    def test_a_type_with_no_file_yet_gets_one_and_a_manifest_line(self):
        (self.folder / "_active.yaml").write_text(
            "resources:\n  - single-answer.yaml\n", encoding="utf-8"
        )

        authoring.save_entry(
            category="nba",
            entry={
                "type": "true-false",
                "slug": "is-it-true",
                "description": "Is it?",
                "level": 2,
                "answer": True,
            },
        )

        created = self.folder / "true-false.yaml"
        self.assertTrue(created.is_file())
        self.assertEqual(self.slugs(created), ["is-it-true"])
        # Without the manifest line the loader would never open the new file,
        # and the create would write real YAML and no row at all.
        self.assertIn(
            "  - true-false.yaml",
            (self.folder / "_active.yaml").read_text(encoding="utf-8"),
        )
        self.assertTrue(TrueFalseQuestion.objects.filter(slug="is-it-true").exists())

    def test_a_slug_another_category_already_uses_is_refused(self):
        self.write_categories([{"slug": "nba", "name": "NBA"}, {"slug": "f1", "name": "F1"}])
        self.write_file("ordering.yaml", [
            {
                "type": "ordering",
                "slug": "taken-elsewhere",
                "description": "Order them.",
                "instruction": "Earliest first.",
                "level": 3,
                "items": ["One", "Two", "Three"],
            }
        ], category="f1")

        with self.assertRaises(ValidationFailed) as refusal:
            authoring.save_entry(
                category="nba", entry=single_answer("taken-elsewhere")
            )

        self.assertIn("f1/ordering.yaml", str(refusal.exception.message))
        # The file is the one it was before the refusal — a slug clash must not
        # leave half an entry behind.
        self.assertEqual(self.slugs(), ["who-scored", "who-else"])


class UpdateTests(AuthoringTestCase):
    def test_an_edit_rewrites_one_block_and_leaves_the_comments(self):
        entry = authoring.read_entry(category="nba", slug="who-scored").entry

        result = authoring.save_entry(
            category="nba",
            entry={**entry, "description": "Who actually won it?", "level": 9},
            original_slug="who-scored",
        )

        self.assertEqual(result.action, "updated")
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("# NBA — single-answer questions.", text)
        self.assertIn("# The oldest one in the file.", text)
        self.assertIn("# A second one, to have something after the first.", text)
        self.assertIn("description: Who actually won it?", text)
        # The untouched entry is byte for byte what it was, nested list and all.
        self.assertIn("    options:\n      - text: Chicago Bulls\n", text)

        question = SingleAnswerQuestion.objects.get(slug="who-scored")
        self.assertEqual(question.description, "Who actually won it?")
        self.assertEqual(question.level, 9)

    def test_the_form_is_seeded_from_the_file_not_the_row(self):
        """The row has the file's clock resolved into it; the entry has not.

        An edit form seeded from the row would send that number back as the
        question's own override, and every question edited from the tester
        would quietly stop tracking its file's tempo.
        """
        self.assertEqual(
            SingleAnswerQuestion.objects.get(slug="who-scored").time_limit_seconds, 10
        )
        entry = authoring.read_entry(category="nba", slug="who-scored").entry
        self.assertNotIn("time_limit_seconds", entry)

    def test_a_rename_moves_the_block_rather_than_copying_it(self):
        entry = authoring.read_entry(category="nba", slug="who-scored").entry

        authoring.save_entry(
            category="nba",
            entry={**entry, "slug": "who-scored-it"},
            original_slug="who-scored",
        )

        self.assertEqual(self.slugs(), ["who-else", "who-scored-it"])
        # The old row survives, stood down by the loader's sweep: somebody's
        # match history points at it.
        self.assertFalse(
            SingleAnswerQuestion.all_objects.get(slug="who-scored").is_active
        )
        self.assertTrue(SingleAnswerQuestion.objects.get(slug="who-scored-it").is_active)

    def test_retyping_moves_the_entry_to_the_other_type_s_file(self):
        authoring.save_entry(
            category="nba",
            entry={
                "type": "ordering",
                "slug": "who-scored-order",
                "description": "Order them.",
                "instruction": "Earliest first.",
                "level": 3,
                "items": ["One", "Two", "Three"],
            },
            original_slug="who-scored",
        )

        self.assertEqual(self.slugs(), ["who-else"])
        self.assertEqual(
            self.slugs(self.folder / "ordering.yaml"), ["who-scored-order"]
        )
        self.assertTrue(OrderingQuestion.objects.filter(slug="who-scored-order").exists())


class RefusalTests(AuthoringTestCase):
    def test_an_invalid_entry_leaves_the_file_exactly_as_it_was(self):
        before = self.path.read_text(encoding="utf-8")

        with self.assertRaises(ValidationFailed):
            authoring.save_entry(
                category="nba",
                # Two correct options — the rule single-answer is named for.
                entry=single_answer(
                    "a-new-one",
                    options=[
                        {"text": "Boston Celtics", "is_correct": True},
                        {"text": "Los Angeles Lakers", "is_correct": True},
                    ],
                ),
            )

        self.assertEqual(self.path.read_text(encoding="utf-8"), before)
        self.assertFalse(SingleAnswerQuestion.objects.filter(slug="a-new-one").exists())

    def test_a_file_this_call_created_is_removed_when_the_load_refuses(self):
        """The rollback has to undo the *file*, not just its contents.

        A first question of a new shape creates the file it goes in. If the
        load then refuses, restoring "what the file was before" is not enough —
        there was no file before, and leaving an empty one behind would fail
        every later load on ``questions`` being empty.
        """
        with self.assertRaises(ValidationFailed):
            authoring.save_entry(
                category="nba",
                entry={
                    "type": "ordering",
                    "slug": "bad-ordering",
                    "description": "Order them.",
                    "instruction": "Earliest first.",
                    "level": 3,
                    # Repeated item — ordering refuses it.
                    "items": ["One", "One", "Three"],
                },
            )

        self.assertFalse((self.folder / "ordering.yaml").exists())

    def test_an_unknown_type_is_refused_before_anything_is_touched(self):
        with self.assertRaises(ValidationFailed):
            authoring.save_entry(
                category="nba", entry=single_answer("a-new-one", type="interpretive-dance")
            )
        self.assertEqual(self.slugs(), ["who-scored", "who-else"])

    def test_a_category_that_escapes_the_resources_tree_is_refused(self):
        with self.assertRaises(ValidationFailed):
            authoring.read_entry(category="../../etc", slug="who-scored")

    def test_a_row_with_no_file_behind_it_says_so(self):
        with self.assertRaises(ValidationFailed) as refusal:
            authoring.read_entry(category="nba", slug="never-authored")
        self.assertIn("never-authored", str(refusal.exception.message))


class DeactivationTests(AuthoringTestCase):
    def test_retiring_a_question_writes_the_line_and_flips_the_column(self):
        result = authoring.set_entry_active(
            category="nba", slug="who-scored", is_active=False
        )

        self.assertIn("is_active: false", self.path.read_text(encoding="utf-8"))
        self.assertFalse(
            SingleAnswerQuestion.all_objects.get(slug="who-scored").is_active
        )
        self.assertEqual(result.action, "updated")

    def test_a_retired_question_stays_retired_across_a_re_sync(self):
        """The whole reason deactivation is a file edit and not a column edit.

        The loader sets ``is_active`` from the file on every run. A tester that
        only flipped the column would have its change undone by the next
        deploy, silently, with the question back in matchmaking.
        """
        authoring.set_entry_active(category="nba", slug="who-scored", is_active=False)
        self.load()

        self.assertFalse(
            SingleAnswerQuestion.all_objects.get(slug="who-scored").is_active
        )

    def test_bringing_one_back_removes_the_line_again(self):
        authoring.set_entry_active(category="nba", slug="who-scored", is_active=False)
        authoring.set_entry_active(category="nba", slug="who-scored", is_active=True)

        self.assertNotIn("is_active", self.path.read_text(encoding="utf-8"))
        self.assertTrue(SingleAnswerQuestion.objects.get(slug="who-scored").is_active)

    def test_deleting_takes_the_block_out_and_stands_the_row_down(self):
        authoring.delete_entry(category="nba", slug="who-scored")

        self.assertEqual(self.slugs(), ["who-else"])
        self.assertFalse(
            SingleAnswerQuestion.all_objects.get(slug="who-scored").is_active
        )
