"""``manage.py questions_report`` — the table, and the exit code.

The exit code is the half that matters. A level band holding fewer questions
than the longest match needs is a band where matchmaking *refuses*
(``selectors.select_questions``), and a command that reports that in a table
nobody reads is a command that lets it ship. Non-zero is what makes it a
deploy's problem rather than two players'.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.questions.constants import LONGEST_MATCH_QUESTION_COUNT
from apps.questions.models import QuestionType

from .factories import QUESTION_FACTORIES, make_category, make_single_answer


def fill(*, category, band_levels=(1, 4, 8), count=LONGEST_MATCH_QUESTION_COUNT) -> None:
    """Stock every band of a category to exactly ``count`` questions."""
    for level in band_levels:
        for index in range(count):
            make_single_answer(
                slug=f"{category.slug}-{level}-{index}", level=level, category=category
            )


class ReportCommandTests(TestCase):
    def setUp(self) -> None:
        self.category = make_category()

    def run_command(self, *args) -> tuple[str, str]:
        out, err = StringIO(), StringIO()
        try:
            call_command("questions_report", *args, stdout=out, stderr=err)
        finally:
            self.out, self.err = out.getvalue(), err.getvalue()
        return self.out, self.err

    def assertFails(self, *args) -> tuple[str, str]:
        """A non-zero exit. ``CommandError`` is how a Django command spells it —
        the same way ``sync_questions`` fails a bad load."""
        with self.assertRaises(CommandError) as caught:
            self.run_command(*args)
        self.failure = caught.exception
        return self.out, self.err

    # --- The table -----------------------------------------------------------

    def test_a_full_catalog_reports_every_band_and_succeeds(self) -> None:
        fill(category=self.category)
        out, _ = self.run_command()

        self.assertIn("Depth by level band", out)
        for band in ("easy", "medium", "hard"):
            self.assertIn(band, out)
        self.assertIn("1-3", out)
        self.assertIn("8-10", out)
        self.assertIn("Every active category can fill", out)

    def test_the_table_breaks_the_catalog_down_by_type(self) -> None:
        """A category that is four hundred single-answers is deep and is also a
        client feature nobody is exercising."""
        fill(category=self.category)
        for question_type, factory in QUESTION_FACTORIES.items():
            factory(slug=f"{question_type}-typed", level=2, category=self.category)

        out, _ = self.run_command()
        self.assertIn("Depth by question type", out)
        self.assertIn("matrix", out)
        self.assertIn("t/f", out)

    def test_the_counts_are_the_ones_a_match_would_find(self) -> None:
        fill(category=self.category)
        QUESTION_FACTORIES[QuestionType.SINGLE_ANSWER](
            slug="retired", level=1, category=self.category
        ).__class__.objects.filter(slug="retired").update(is_active=False)

        out, _ = self.run_command()
        # Seven per band, and the retired eighth counted by neither.
        self.assertIn("21", out)

    # --- The exit code -------------------------------------------------------

    def test_a_thin_band_fails_the_command(self) -> None:
        fill(category=self.category)
        self.category.singleanswerquestions.filter(level=8).delete()

        out, err = self.assertFails()

        self.assertIn("hard", err)
        self.assertIn("cannot fill", str(self.failure))
        self.assertIn("NO (needs 7)", out, "the table says which band, not just that one is")

    def test_an_empty_catalog_fails_rather_than_reporting_nothing_wrong(self) -> None:
        self.assertFails()
        self.assertIn("cannot fill", str(self.failure))

    def test_a_band_exactly_full_passes(self) -> None:
        """The boundary the matchmaker will hit: ``select_questions`` refuses
        when the pool is *smaller* than the count, so equal is playable."""
        fill(category=self.category, count=LONGEST_MATCH_QUESTION_COUNT)
        self.run_command()
        self.assertIn("Every active category can fill", self.out)

    def test_count_lowers_the_bar(self) -> None:
        """For asking "could we run 3-question matches today?" while the catalog
        is still being written."""
        fill(category=self.category, count=3)
        self.assertFails()

        out, _ = self.run_command("--count", "3")
        self.assertIn("Every active category can fill", out)

    def test_a_nonsense_count_is_refused(self) -> None:
        fill(category=self.category)
        with self.assertRaises(CommandError):
            self.run_command("--count", "0")

    # --- Which categories count ---------------------------------------------

    def test_an_inactive_category_is_neither_reported_nor_a_failure(self) -> None:
        """It cannot be played, so its being thin is not a gap to fix."""
        fill(category=self.category)
        offseason = make_category(slug="f1", name="F1", is_active=False)
        make_single_answer(slug="f1-only", level=1, category=offseason)

        out, _ = self.run_command()
        self.assertNotIn("f1", out)
        self.assertIn("Every active category can fill", out)

    def test_include_inactive_reports_it_without_failing_on_it(self) -> None:
        fill(category=self.category)
        offseason = make_category(slug="f1", name="F1", is_active=False)
        make_single_answer(slug="f1-only", level=1, category=offseason)

        out, _ = self.run_command("--include-inactive")
        self.assertIn("f1", out)
        self.assertIn("(off)", out)
        self.assertIn("Every active category can fill", out)

    def test_one_category_can_be_reported_on_alone(self) -> None:
        fill(category=self.category)
        other = make_category(slug="f1", name="F1")
        make_single_answer(slug="f1-only", level=1, category=other)

        out, _ = self.run_command("--category", "nba")
        self.assertIn("nba", out)
        self.assertNotIn("f1", out)

    def test_an_unknown_category_is_refused(self) -> None:
        with self.assertRaises(CommandError):
            self.run_command("--category", "curling")

    def test_the_shortfall_to_the_stocking_target_is_reported_not_enforced(self) -> None:
        """``CATALOG_DEPTH_TARGET`` is where a band stops being the same board
        every time. It is a content gap, so it prints a number and does not fail
        the command — refusing would take a category out of service for being
        merely repetitive."""
        fill(category=self.category)
        out, _ = self.run_command()

        self.assertIn("to target", out)
        self.assertIn("+43", out)  # 50 - 7
        self.assertIn("Every active category can fill", out)
