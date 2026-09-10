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
    DEFAULT_PROBABILITY_SCORE,
    QUESTION_MODELS,
    ColumnsRowsQuestion,
    FreeTextQuestion,
    MatrixCellAnswer,
    MatrixKind,
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
                        {
                            "row": "Bulls",
                            "column": "1990s",
                            "answers": [
                                {"answer": "1996", "probability_score": 2},
                                "1998",
                            ],
                        },
                        {"row": "Lakers", "column": "2000s", "answers": ["2001"]},
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

    def test_a_cell_keeps_every_answer_it_was_authored_with(self) -> None:
        question = ColumnsRowsQuestion.objects.get(slug="grid")
        cell = question.cells.get(row__title="Bulls", column__title="1990s")
        self.assertEqual(
            [(a.value, a.probability_score) for a in cell.answers.all()],
            # Ordered by grade: the graded 1996 before the shorthand 1998, which
            # took DEFAULT_PROBABILITY_SCORE for want of a grade.
            [("1996", 2), ("1998", DEFAULT_PROBABILITY_SCORE)],
        )

    def test_a_cells_answers_land_on_the_cell_they_were_authored_under(self) -> None:
        """The loader pairs bulk-created cells with their spec by position, so a
        grid whose cells are written out of row order would be the way that
        pairing breaks."""
        question = ColumnsRowsQuestion.objects.get(slug="grid")
        cell = question.cells.get(row__title="Lakers", column__title="2000s")
        self.assertEqual([a.value for a in cell.answers.all()], ["2001"])

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

    def test_a_question_that_does_not_author_a_time_limit_stores_none(self) -> None:
        # "single" (above) never mentions time_limit_seconds — the row must say
        # so explicitly, rather than default to some number of its own, so
        # apps.matches's fallbacks are the only place that decides one.
        self.assertIsNone(SingleAnswerQuestion.objects.get(slug="single").time_limit_seconds)


class TimeLimitSecondsTests(ResourceTreeTestCase):
    """A question may author its own ``time_limit_seconds`` — the override
    ``apps.matches.constants.time_limit_ms_for`` reads ahead of every
    fallback."""

    def test_an_authored_time_limit_reaches_the_row(self) -> None:
        self.write_file("timed.yaml", [single_answer("timed", time_limit_seconds=45)])
        self.load()
        self.assertEqual(SingleAnswerQuestion.objects.get(slug="timed").time_limit_seconds, 45)

    def test_a_time_limit_outside_the_allowed_range_is_refused(self) -> None:
        self.write_file("too-long.yaml", [single_answer("too-long", time_limit_seconds=601)])
        with self.assertRaises(ValidationFailed):
            self.load()


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


class TeamMatrixTests(ResourceTreeTestCase):
    """``kind: teams`` — the grid whose cells the loader derives.

    Loaded through a resource tree rather than built by a factory, because what
    is being tested *is* the loader: which intersections it writes, which it
    leaves out, and that it writes no answers at all.
    """

    def _grid(self, **overrides) -> dict:
        return {
            "type": "matrix",
            "kind": "teams",
            "slug": "team-grid",
            "description": "Name a player who played for both.",
            "level": 6,
            "rows": ["Chicago Bulls", "Boston Celtics"],
            "columns": ["Los Angeles Lakers", "Miami Heat"],
            **overrides,
        }

    def load_grid(self, **overrides) -> ColumnsRowsQuestion:
        self.write_file("q.yaml", [self._grid(**overrides)])
        self.load()
        return ColumnsRowsQuestion.objects.get(slug=overrides.get("slug", "team-grid"))

    def test_the_cells_are_derived_rather_than_authored(self) -> None:
        question = self.load_grid()
        self.assertEqual(question.kind, MatrixKind.TEAMS)
        self.assertEqual(
            {(cell.row.title, cell.column.title) for cell in question.cells.all()},
            {
                ("Chicago Bulls", "Los Angeles Lakers"),
                ("Chicago Bulls", "Miami Heat"),
                ("Boston Celtics", "Los Angeles Lakers"),
                ("Boston Celtics", "Miami Heat"),
            },
        )

    def test_it_writes_no_answers(self) -> None:
        """The whole point of the kind: the answer key is the artifact, not tens
        of thousands of rows per question."""
        question = self.load_grid()
        self.assertEqual(
            MatrixCellAnswer.objects.filter(cell__question=question).count(), 0
        )

    def test_a_franchise_against_itself_is_not_a_cell(self) -> None:
        """Its answer is everybody who ever wore the shirt, which is not a
        question."""
        question = self.load_grid(
            rows=["Chicago Bulls", "Boston Celtics"],
            columns=["Chicago Bulls", "Miami Heat"],
        )
        self.assertNotIn(
            ("Chicago Bulls", "Chicago Bulls"),
            {(cell.row.title, cell.column.title) for cell in question.cells.all()},
        )

    def test_a_pairing_that_never_shared_a_player_is_not_a_cell(self) -> None:
        """Sparse, decided by the artifact rather than by an author — so a
        player is never given an input for a square nobody can fill."""
        question = self.load_grid(
            rows=["Anderson Packers", "Chicago Bulls"],
            columns=["Miami Heat", "Los Angeles Lakers"],
        )
        pairs = {(cell.row.title, cell.column.title) for cell in question.cells.all()}
        self.assertNotIn(("Anderson Packers", "Miami Heat"), pairs)
        self.assertIn(("Chicago Bulls", "Miami Heat"), pairs)

    def test_headings_take_the_artifacts_spelling(self) -> None:
        question = self.load_grid(rows=["chicago  BULLS", "Boston Celtics"])
        self.assertEqual(question.rows.first().title, "Chicago Bulls")

    def test_counts_are_still_derived_from_the_headings(self) -> None:
        question = self.load_grid()
        self.assertEqual((question.row_count, question.column_count), (2, 2))

    def test_a_reload_replaces_the_grid_rather_than_doubling_it(self) -> None:
        self.load_grid()
        self.load()
        question = ColumnsRowsQuestion.objects.get(slug="team-grid")
        self.assertEqual(question.cells.count(), 4)


class TeamMatrixRefusalTests(ResourceTreeTestCase):
    """What a ``kind: teams`` grid may not say."""

    def _grid(self, **overrides) -> dict:
        return {
            "type": "matrix",
            "kind": "teams",
            "slug": "team-grid",
            "description": "Name a player who played for both.",
            "level": 6,
            "rows": ["Chicago Bulls", "Boston Celtics"],
            "columns": ["Los Angeles Lakers", "Miami Heat"],
            **overrides,
        }

    def assertRefused(self, *needles: str):
        with self.assertRaises(ValidationFailed) as caught:
            self.load()
        text = " ".join([caught.exception.message, *(caught.exception.details or [])])
        for needle in needles:
            self.assertIn(needle, text)
        return text

    def test_a_heading_naming_no_franchise(self) -> None:
        """Caught at load time, where a mistyped franchise is a fixable typo —
        rather than at play time, where it is a column no answer can fill."""
        self.write_file("q.yaml", [self._grid(rows=["LA Lakers", "Boston Celtics"])])
        self.assertRefused("LA Lakers", "no NBA franchise")

    def test_authoring_cells_as_well(self) -> None:
        """Two answer keys for one grid is an author who believes one of them is
        in charge; guessing which would make the other silently do nothing."""
        self.write_file(
            "q.yaml",
            [
                self._grid(
                    cells=[
                        {
                            "row": "Chicago Bulls",
                            "column": "Los Angeles Lakers",
                            "answers": ["Dennis Rodman"],
                        }
                    ]
                )
            ],
        )
        self.assertRefused("may not author them")

    def test_franchises_that_never_shared_a_player_at_all(self) -> None:
        """A grid with no fillable square is not a hard question, it is a broken
        one — and only the artifact can tell, since every heading is a perfectly
        real franchise."""
        self.write_file(
            "q.yaml",
            [
                self._grid(
                    rows=["Anderson Packers", "Chicago Stags"],
                    columns=["Miami Heat", "Charlotte Bobcats"],
                )
            ],
        )
        self.assertRefused("no cell anybody could fill")

    def test_an_authored_grid_with_no_cells(self) -> None:
        """The other half of the same rule: only a derived grid may leave its
        cells out."""
        self.write_file("q.yaml", [self._grid(kind="authored")])
        self.assertRefused("needs at least one cell")

    def test_a_kind_nobody_has_heard_of(self) -> None:
        self.write_file("q.yaml", [self._grid(kind="players")])
        self.assertRefused("q.yaml")


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
                    "cells": [
                        {"row": "Heat", "column": "1990s", "answers": ["x"]}
                    ],
                }
            ],
        )
        self.assertRefused("bad-grid", "undeclared row")

    def _grid(self, slug: str, cells: list[dict]) -> dict:
        return {
            "type": "matrix",
            "slug": slug,
            "description": "Fill it.",
            "level": 4,
            "rows": ["Bulls", "Lakers"],
            "columns": ["1990s", "2000s"],
            "cells": cells,
        }

    def test_a_matrix_cell_with_no_answers_at_all(self) -> None:
        """A cell nobody can fill is a cell that silently caps the question's
        credit, so it is refused at authoring time rather than discovered as a
        grid no player can complete."""
        self.write_file(
            "q.yaml",
            [self._grid("empty-cell", [{"row": "Bulls", "column": "1990s", "answers": []}])],
        )
        self.assertRefused("q.yaml")

    def test_a_matrix_cell_repeating_an_answer(self) -> None:
        """Two entries differing only in case are one answer written twice —
        with two different grades, and no way to say which one holds."""
        self.write_file(
            "q.yaml",
            [
                self._grid(
                    "repeated-answer",
                    [
                        {
                            "row": "Bulls",
                            "column": "1990s",
                            "answers": [
                                {"answer": "Michael Jordan", "probability_score": 2},
                                {"answer": "michael jordan", "probability_score": 9},
                            ],
                        }
                    ],
                )
            ],
        )
        self.assertRefused("repeats an answer")

    def test_a_probability_score_off_the_scale(self) -> None:
        self.write_file(
            "q.yaml",
            [
                self._grid(
                    "over-graded",
                    [
                        {
                            "row": "Bulls",
                            "column": "1990s",
                            "answers": [{"answer": "1996", "probability_score": 11}],
                        }
                    ],
                )
            ],
        )
        self.assertRefused("q.yaml")

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
