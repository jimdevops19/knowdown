"""The question pipeline: what the loader does, and what it refuses.

The tests that matter here are the *refusals*. A loader that writes what it is
given is easy; the value is in a bad file failing the load with a message naming
the question, instead of reaching the database and surfacing weeks later as a
question two players cannot answer.

Fixtures are written to a temporary resources tree rather than asserted against
``apps/questions/resources/`` — the real catalog is content that will change
every week, and a test that counts its rows is a test that fails on every
question anyone adds.
"""

from __future__ import annotations

import shutil
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.categories.models import Category
from apps.core_common.exceptions import ValidationFailed
from apps.questions.models import (
    QUESTION_MODELS,
    ColumnsRowsQuestion,
    FreeTextQuestion,
    OrderingQuestion,
    QuestionType,
    SingleAnswerImageQuestion,
    SingleAnswerQuestion,
    TrueFalseQuestion,
)
from apps.questions.services import sync

#: A real PNG from the shipped catalog, so the image tests exercise a file
#: Pillow and the ImageField both accept rather than a made-up byte string.
REAL_IMAGE = (
    Path(sync.RESOURCES) / "nba" / "images" / "court-free-throw-line.png"
)


def single_answer(slug: str = "who-scored", **overrides) -> dict:
    entry = {
        "type": "single-answer",
        "slug": slug,
        "description": "Who won it?",
        "level": 3,
        "options": [
            {"text": "Boston Celtics", "is_correct": True},
            {"text": "Los Angeles Lakers"},
        ],
    }
    return entry | overrides


class ResourceTreeTestCase(TestCase):
    """Runs the loader against a resources tree this test wrote itself."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        self._media = TemporaryDirectory()
        self.media_root = Path(self._media.name)
        self.addCleanup(self._media.cleanup)

        patch = override_settings(MEDIA_ROOT=self.media_root)
        patch.enable()
        self.addCleanup(patch.disable)

        # The loader resolves both paths off module constants, so a test tree is
        # a matter of pointing those at it.
        self._real_resources = sync.RESOURCES
        self._real_categories = sync.CATEGORIES_FILE
        sync.RESOURCES = self.root
        sync.CATEGORIES_FILE = self.root / "categories.yaml"
        self.addCleanup(self._restore_paths)

        self.write_categories([{"slug": "nba", "name": "NBA"}])

    def _restore_paths(self) -> None:
        sync.RESOURCES = self._real_resources
        sync.CATEGORIES_FILE = self._real_categories

    def write_categories(self, entries: list[dict]) -> None:
        (self.root / "categories.yaml").write_text(yaml.safe_dump(entries))

    def write_file(self, name: str, questions: list[dict], *, category: str = "nba") -> Path:
        folder = self.root / category
        folder.mkdir(exist_ok=True)
        path = folder / name
        path.write_text(yaml.safe_dump({"category": category, "questions": questions}))
        return path

    def add_image(self, name: str, *, category: str = "nba") -> None:
        images = self.root / category / "images"
        images.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_IMAGE, images / name)

    def load(self, **kwargs) -> sync.LoadReport:
        sync.sync_categories()
        return sync.sync_questions(**kwargs)


class LoadEveryTypeTests(ResourceTreeTestCase):
    """One entry of each shape, loaded into the right table with its children."""

    def setUp(self) -> None:
        super().setUp()
        self.add_image("a.png")
        self.add_image("b.png")
        self.write_file(
            "everything.yaml",
            [
                single_answer("single"),
                {
                    "type": "image-answer",
                    "slug": "images",
                    "description": "Which court?",
                    "level": 1,
                    "options": [
                        {"image": "a.png", "is_correct": True, "label": "A"},
                        {"image": "b.png"},
                    ],
                },
                {
                    "type": "multiple-answer",
                    "slug": "several",
                    "description": "Which of these?",
                    "level": 5,
                    "options": [
                        {"text": "One", "is_correct": True},
                        {"text": "Two", "is_correct": True},
                        {"text": "Three"},
                    ],
                },
                {
                    "type": "true-false",
                    "slug": "claim",
                    "description": "A statement.",
                    "level": 2,
                    "answer": True,
                },
                {
                    "type": "free-text",
                    "slug": "typed",
                    "description": "Name the player.",
                    "level": 3,
                    "accepted_answers": ["Kobe Bryant", "Kobe"],
                },
                {
                    "type": "ordering",
                    "slug": "sorted",
                    "description": "Four seasons.",
                    "instruction": "Earliest first.",
                    "level": 4,
                    "items": ["1991", "1992", "1993"],
                },
                {
                    "type": "matrix",
                    "slug": "grid",
                    "description": "Fill the grid.",
                    "level": 6,
                    "rows": ["Bulls", "Lakers"],
                    "columns": ["1990s", "2000s"],
                    "cells": [
                        {"row": "Bulls", "column": "1990s", "answer": "1996"},
                        {"row": "Lakers", "column": "2000s", "answer": "2001"},
                    ],
                },
            ],
        )
        self.report = self.load()

    def test_every_type_landed_in_its_own_table(self) -> None:
        self.assertEqual(len(self.report.created), 7)
        for model in QUESTION_MODELS.values():
            self.assertEqual(model.objects.count(), 1, model.__name__)

    def test_options_are_numbered_in_the_authored_order(self) -> None:
        question = SingleAnswerQuestion.objects.get(slug="single")
        self.assertEqual(
            [(o.order, o.text, o.is_correct) for o in question.options.all()],
            [(1, "Boston Celtics", True), (2, "Los Angeles Lakers", False)],
        )

    def test_ordering_positions_are_derived_from_the_list(self) -> None:
        question = OrderingQuestion.objects.get(slug="sorted")
        self.assertEqual(
            [(o.correct_position, o.text) for o in question.options.all()],
            [(1, "1991"), (2, "1992"), (3, "1993")],
        )

    def test_matrix_counts_are_derived_from_the_headings(self) -> None:
        question = ColumnsRowsQuestion.objects.get(slug="grid")
        self.assertEqual((question.row_count, question.column_count), (2, 2))
        # Sparse: two of the four intersections were authored.
        self.assertEqual(question.cells.count(), 2)

    def test_true_false_stores_its_answer_without_options(self) -> None:
        self.assertIs(TrueFalseQuestion.objects.get(slug="claim").answer, True)

    def test_free_text_keeps_every_accepted_spelling(self) -> None:
        question = FreeTextQuestion.objects.get(slug="typed")
        self.assertEqual(
            sorted(a.value for a in question.accepted_answers.all()),
            ["Kobe", "Kobe Bryant"],
        )

    def test_option_images_are_copied_under_media_root(self) -> None:
        option = SingleAnswerImageQuestion.objects.get(slug="images").options.first()
        self.assertEqual(option.image.name, "questions/answers/nba/a.png")
        self.assertTrue((self.media_root / option.image.name).is_file())

    def test_question_type_names_the_yaml_key(self) -> None:
        self.assertEqual(
            SingleAnswerQuestion.objects.get(slug="single").question_type,
            QuestionType.SINGLE_ANSWER,
        )


class IdempotencyTests(ResourceTreeTestCase):
    """Re-running is how a question is *edited*, so a second load must correct
    rows rather than duplicate them."""

    def test_second_load_updates_and_creates_nothing(self) -> None:
        self.write_file("q.yaml", [single_answer()])
        self.load()
        second = self.load()

        self.assertEqual(second.created, [])
        self.assertEqual(second.updated, ["who-scored"])
        self.assertEqual(SingleAnswerQuestion.objects.count(), 1)

    def test_an_edit_reaches_the_row_and_its_options(self) -> None:
        self.write_file("q.yaml", [single_answer()])
        self.load()
        original_id = SingleAnswerQuestion.objects.get().id

        self.write_file(
            "q.yaml",
            [
                single_answer(
                    description="Who really won it?",
                    level=9,
                    options=[
                        {"text": "Chicago Bulls", "is_correct": True},
                        {"text": "Boston Celtics"},
                        {"text": "Miami Heat"},
                    ],
                )
            ],
        )
        self.load()

        question = SingleAnswerQuestion.objects.get()
        self.assertEqual(question.id, original_id, "the row is corrected, not replaced")
        self.assertEqual(question.description, "Who really won it?")
        self.assertEqual(question.level, 9)
        self.assertEqual(
            [o.text for o in question.options.all()],
            ["Chicago Bulls", "Boston Celtics", "Miami Heat"],
        )

    def test_unchanged_images_are_not_recopied(self) -> None:
        self.add_image("a.png")
        self.add_image("b.png")
        entry = {
            "type": "image-answer",
            "slug": "images",
            "description": "Which court?",
            "level": 1,
            "options": [{"image": "a.png", "is_correct": True}, {"image": "b.png"}],
        }
        self.write_file("q.yaml", [entry])
        self.load()

        copied = self.media_root / "questions/answers/nba/a.png"
        before = copied.stat().st_mtime_ns
        self.load()
        self.assertEqual(copied.stat().st_mtime_ns, before)


class DeactivationTests(ResourceTreeTestCase):
    """A question is somebody's match history, so it is stood down, not removed."""

    def test_a_dropped_question_is_deactivated_not_deleted(self) -> None:
        self.write_file("q.yaml", [single_answer("kept"), single_answer("dropped")])
        self.load()

        self.write_file("q.yaml", [single_answer("kept")])
        report = self.load()

        self.assertEqual(report.deactivated, ["dropped"])
        self.assertEqual(SingleAnswerQuestion.objects.count(), 2)
        self.assertFalse(SingleAnswerQuestion.objects.get(slug="dropped").is_active)
        self.assertTrue(SingleAnswerQuestion.objects.get(slug="kept").is_active)

    def test_a_question_that_comes_back_is_reactivated(self) -> None:
        self.write_file("q.yaml", [single_answer("seasonal")])
        self.load()
        self.write_file("q.yaml", [single_answer("filler")])
        self.load()

        self.write_file("q.yaml", [single_answer("seasonal")])
        self.load()
        self.assertTrue(SingleAnswerQuestion.objects.get(slug="seasonal").is_active)

    def test_loading_one_category_leaves_another_alone(self) -> None:
        """The sweep is scoped to what was loaded — otherwise ``--category nba``
        would quietly retire every other sport."""
        self.write_categories(
            [{"slug": "nba", "name": "NBA"}, {"slug": "f1", "name": "F1"}]
        )
        self.write_file("q.yaml", [single_answer("hoops")])
        self.write_file("q.yaml", [single_answer("cars")], category="f1")
        self.load()

        report = self.load(category="nba")

        self.assertEqual(report.deactivated, [])
        self.assertTrue(SingleAnswerQuestion.objects.get(slug="cars").is_active)


class RefusalTests(ResourceTreeTestCase):
    """Every one of these must fail the load, naming what is wrong."""

    def assertRefused(self, *needles: str):
        with self.assertRaises(ValidationFailed) as caught:
            self.load()
        text = " ".join([caught.exception.message, *(caught.exception.details or [])])
        for needle in needles:
            self.assertIn(needle, text)
        return text

    def test_two_correct_options_on_a_single_answer(self) -> None:
        self.write_file(
            "q.yaml",
            [
                single_answer(
                    "ambiguous",
                    options=[
                        {"text": "A", "is_correct": True},
                        {"text": "B", "is_correct": True},
                    ],
                )
            ],
        )
        self.assertRefused("ambiguous", "exactly one option")

    def test_no_correct_option_at_all(self) -> None:
        self.write_file(
            "q.yaml",
            [single_answer("unanswerable", options=[{"text": "A"}, {"text": "B"}])],
        )
        self.assertRefused("unanswerable", "exactly one option")

    def test_a_multiple_answer_with_one_correct_option(self) -> None:
        self.write_file(
            "q.yaml",
            [
                {
                    "type": "multiple-answer",
                    "slug": "mislabelled",
                    "description": "Which?",
                    "level": 3,
                    "options": [
                        {"text": "A", "is_correct": True},
                        {"text": "B"},
                        {"text": "C"},
                    ],
                }
            ],
        )
        self.assertRefused("mislabelled", "at least two correct")

    def test_a_duplicate_slug_across_two_files_names_both(self) -> None:
        self.write_file("first.yaml", [single_answer("twice")])
        self.write_file("second.yaml", [single_answer("twice")])
        self.assertRefused("twice", "first.yaml", "second.yaml")

    def test_a_missing_image_names_the_question(self) -> None:
        self.write_file(
            "q.yaml",
            [
                {
                    "type": "image-answer",
                    "slug": "broken-picture",
                    "description": "Which court?",
                    "level": 1,
                    "options": [
                        {"image": "gone.png", "is_correct": True},
                        {"image": "also-gone.png"},
                    ],
                }
            ],
        )
        with self.assertRaises(ValidationFailed) as caught:
            self.load()
        self.assertIn("broken-picture", caught.exception.message)
        self.assertIn("gone.png", caught.exception.message)

    def test_a_matrix_cell_naming_an_undeclared_heading(self) -> None:
        self.write_file(
            "q.yaml",
            [
                {
                    "type": "matrix",
                    "slug": "bad-grid",
                    "description": "Fill it.",
                    "level": 4,
                    "rows": ["Bulls", "Lakers"],
                    "columns": ["1990s", "2000s"],
                    "cells": [{"row": "Heat", "column": "1990s", "answer": "x"}],
                }
            ],
        )
        self.assertRefused("bad-grid", "undeclared row")

    def test_an_unknown_key_is_not_silently_ignored(self) -> None:
        self.write_file("q.yaml", [single_answer("typo", **{"levl": 4})])
        self.assertRefused("q.yaml")

    def test_a_level_outside_the_scale(self) -> None:
        self.write_file("q.yaml", [single_answer("too-hard", level=11)])
        self.assertRefused("q.yaml")

    def test_a_file_declaring_a_category_it_does_not_sit_in(self) -> None:
        folder = self.root / "nba"
        folder.mkdir(exist_ok=True)
        (folder / "q.yaml").write_text(
            yaml.safe_dump({"category": "f1", "questions": [single_answer()]})
        )
        self.assertRefused("declares category", "f1")

    def test_a_category_with_no_row_behind_it(self) -> None:
        self.write_file("q.yaml", [single_answer("orphan")], category="f1")
        with self.assertRaises(ValidationFailed) as caught:
            self.load()
        self.assertIn("Unknown categories", caught.exception.message)

    def test_a_question_changing_type_under_the_same_slug(self) -> None:
        self.write_file("q.yaml", [single_answer("shapeshifter")])
        self.load()

        self.write_file(
            "q.yaml",
            [
                {
                    "type": "true-false",
                    "slug": "shapeshifter",
                    "description": "A statement.",
                    "level": 2,
                    "answer": True,
                }
            ],
        )
        self.assertRefused("shapeshifter", "already stored as single-answer")

    def test_nothing_is_written_when_the_last_file_is_bad(self) -> None:
        """The whole point of parsing everything up front."""
        self.write_file("a.yaml", [single_answer("fine")])
        self.write_file("z.yaml", [single_answer("broken", level=99)])
        with self.assertRaises(ValidationFailed):
            self.load()
        self.assertEqual(SingleAnswerQuestion.objects.count(), 0)


class CategorySyncTests(ResourceTreeTestCase):
    def test_categories_are_upserted_on_slug(self) -> None:
        self.write_categories([{"slug": "nba", "name": "NBA", "description": "Hoops."}])
        sync.sync_categories()
        self.write_categories([{"slug": "nba", "name": "NBA", "description": "Basketball."}])
        report = sync.sync_categories()

        self.assertEqual(report.updated, ["nba"])
        self.assertEqual(Category.objects.count(), 1)
        self.assertEqual(Category.objects.get().description, "Basketball.")

    def test_a_dropped_category_is_deactivated(self) -> None:
        self.write_categories(
            [{"slug": "nba", "name": "NBA"}, {"slug": "f1", "name": "F1"}]
        )
        sync.sync_categories()
        self.write_categories([{"slug": "nba", "name": "NBA"}])
        report = sync.sync_categories()

        self.assertEqual(report.deactivated, ["f1"])
        self.assertFalse(Category.all_objects.get(slug="f1").is_active)


class CommandTests(ResourceTreeTestCase):
    """The command wrapper: its flags, and that a bad load exits non-zero.

    Output is captured rather than printed — the command's whole job is to
    report, and a passing suite that prints its reports is a suite whose real
    failures scroll past.
    """

    def run_command(self, *args) -> str:
        out, err = StringIO(), StringIO()
        call_command("sync_questions", *args, stdout=out, stderr=err)
        return out.getvalue()

    def test_dry_run_reports_and_writes_nothing(self) -> None:
        self.write_file("q.yaml", [single_answer()])
        self.run_command("--dry-run")

        self.assertEqual(SingleAnswerQuestion.objects.count(), 0)
        self.assertEqual(Category.objects.count(), 0)

    def test_a_plain_run_writes(self) -> None:
        self.write_file("q.yaml", [single_answer()])
        self.run_command()

        self.assertEqual(SingleAnswerQuestion.objects.count(), 1)

    def test_categories_only_stops_before_the_questions(self) -> None:
        self.write_file("q.yaml", [single_answer()])
        self.run_command("--categories-only")

        self.assertEqual(Category.objects.count(), 1)
        self.assertEqual(SingleAnswerQuestion.objects.count(), 0)

    def test_a_bad_file_exits_with_a_command_error(self) -> None:
        self.write_file("q.yaml", [single_answer("bad", level=99)])
        with self.assertRaises(CommandError):
            self.run_command()

    def test_an_unknown_category_folder_is_refused(self) -> None:
        self.write_file("q.yaml", [single_answer()])
        with self.assertRaises(CommandError):
            self.run_command("--category", "f1")


class ShippedCatalogTests(TestCase):
    """The real ``resources/`` tree loads.

    Deliberately asserts almost nothing about *what* is in it — the catalog is
    content, and a test counting its questions fails every time somebody writes
    one. What it does guard is that the shipped files stay loadable, which is the
    thing a bad merge breaks.
    """

    def test_the_shipped_resources_load(self) -> None:
        with TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                categories, questions = sync.load_resources()

        self.assertEqual(categories.deactivated, [])
        self.assertEqual(questions.deactivated, [])
        self.assertTrue(questions.created, "the catalog is empty")
        # Every shape is exercised by the shipped catalog, so a question type
        # that stops loading is caught here rather than the first time somebody
        # writes one of that kind.
        for question_type, model in QUESTION_MODELS.items():
            self.assertTrue(
                model.objects.exists(),
                f"the shipped catalog has no {question_type} question",
            )
