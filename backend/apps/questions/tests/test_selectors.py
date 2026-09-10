"""Drawing a matchup's questions, and knowing whether one can be drawn.

The rule under most of this: **a thin category is a broken match, not a shorter
one**. ``select_questions`` refuses rather than returning what it has, because
silently playing four questions instead of seven would make the length of a
match depend on how well stocked a category happens to be — a rule nobody
agreed to, and one that would change under two players mid-season as questions
are retired.
"""

from __future__ import annotations

import random

from django.test import TestCase

from apps.core_common.exceptions import NotFound, ValidationFailed
from apps.questions import selectors
from apps.questions.constants import LEVEL_BANDS
from apps.questions.models import QUESTION_MODELS, QuestionType

from .factories import QUESTION_FACTORIES, make_category, make_single_answer


def stock(*, category, levels, slug_prefix="q") -> None:
    """One single-answer question at each of ``levels``."""
    for index, level in enumerate(levels):
        make_single_answer(
            slug=f"{slug_prefix}-{index}", level=level, category=category
        )


class SelectQuestionsTests(TestCase):
    def setUp(self) -> None:
        self.category = make_category()

    def test_a_pool_the_size_of_the_match_is_drawn_whole(self) -> None:
        stock(category=self.category, levels=[3, 3, 3])
        refs = selectors.select_questions(category=self.category, count=3)

        self.assertEqual(len(refs), 3)
        self.assertEqual(len({ref.question_id for ref in refs}), 3, "no repeats")

    def test_a_thin_pool_is_refused_rather_than_shortened(self) -> None:
        stock(category=self.category, levels=[3, 3])

        with self.assertRaises(ValidationFailed) as caught:
            selectors.select_questions(category=self.category, count=7)

        self.assertEqual(caught.exception.code, "not_enough_questions")
        self.assertIn("nba", caught.exception.message)
        self.assertIn("7", caught.exception.message)

    def test_the_refusal_counts_what_can_be_asked_not_what_exists(self) -> None:
        """A deactivated question is still a row and is not a question anyone can
        be asked, so it must not make a thin band look playable."""
        stock(category=self.category, levels=[3, 3, 3])
        selectors.select_questions(category=self.category, count=3)  # fine today

        QUESTION_MODELS[QuestionType.SINGLE_ANSWER].objects.filter(
            slug="q-0"
        ).update(is_active=False)

        with self.assertRaises(ValidationFailed):
            selectors.select_questions(category=self.category, count=3)

    def test_another_categorys_questions_do_not_count(self) -> None:
        stock(category=self.category, levels=[3])
        stock(
            category=make_category(slug="f1", name="F1"),
            levels=[3, 3, 3],
            slug_prefix="f1",
        )

        with self.assertRaises(ValidationFailed):
            selectors.select_questions(category=self.category, count=3)

    def test_a_draw_spans_every_answer_shape(self) -> None:
        """The registry walk is the whole reason selection lives in this app: one
        match can mix a matrix, a true/false and an ordering, and the match
        engine never learns that those are different tables."""
        for question_type, factory in QUESTION_FACTORIES.items():
            factory(slug=f"{question_type}-drawn", category=self.category)

        refs = selectors.select_questions(
            category=self.category, count=len(QUESTION_FACTORIES)
        )
        self.assertEqual(
            {ref.question_type for ref in refs}, set(QUESTION_MODELS)
        )

    def test_a_level_band_narrows_the_pool(self) -> None:
        stock(category=self.category, levels=[1, 2, 3, 9, 10])
        easy = LEVEL_BANDS[0]

        refs = selectors.select_questions(
            category=self.category, count=3, level_range=easy.level_range
        )
        levels = {
            selectors.get_question(ref=ref).level for ref in refs
        }
        self.assertTrue(levels <= {1, 2, 3})

        with self.assertRaises(ValidationFailed):
            selectors.select_questions(
                category=self.category, count=4, level_range=easy.level_range
            )

    def test_a_nonsense_level_band_is_refused(self) -> None:
        stock(category=self.category, levels=[1, 2, 3])
        for level_range in ((3, 1), (0, 4), (1, 99)):
            with self.subTest(level_range=level_range):
                with self.assertRaises(ValidationFailed):
                    selectors.select_questions(
                        category=self.category, count=1, level_range=level_range
                    )

    def test_tags_filter_by_containment(self) -> None:
        """A themed round is built out of the same catalog, and a question with
        extra facets still belongs in a narrower one."""
        make_single_answer(
            slug="finals", category=self.category
        ).__class__.objects.filter(slug="finals").update(
            tags={"era": "2000s", "stage": "finals"}
        )
        make_single_answer(slug="regular", category=self.category)

        refs = selectors.select_questions(
            category=self.category, count=1, tags={"era": "2000s"}
        )
        self.assertEqual(selectors.get_question(ref=refs[0]).slug, "finals")

    def test_a_single_type_round_is_a_legitimate_thing_to_ask_for(self) -> None:
        make_single_answer(slug="text-one", category=self.category)
        QUESTION_FACTORIES[QuestionType.TRUE_FALSE](
            slug="tf-one", category=self.category
        )

        refs = selectors.select_questions(
            category=self.category, count=1, types=[QuestionType.TRUE_FALSE]
        )
        self.assertEqual(refs[0].question_type, QuestionType.TRUE_FALSE)

    def test_an_unknown_type_is_refused_rather_than_ignored(self) -> None:
        stock(category=self.category, levels=[1])
        with self.assertRaises(ValidationFailed) as caught:
            selectors.select_questions(
                category=self.category, count=1, types=["telepathy"]
            )
        self.assertIn("telepathy", caught.exception.message)

    def test_a_match_of_no_questions_is_refused(self) -> None:
        with self.assertRaises(ValidationFailed):
            selectors.select_questions(category=self.category, count=0)

    def test_an_injected_rng_pins_the_draw(self) -> None:
        """What makes "the server picks once, for both players" testable — and
        the reason ``rng`` is a parameter rather than a module-level seed."""
        stock(category=self.category, levels=[1, 2, 3, 4, 5, 6, 7])

        first = selectors.select_questions(
            category=self.category, count=5, rng=random.Random(7)
        )
        second = selectors.select_questions(
            category=self.category, count=5, rng=random.Random(7)
        )
        self.assertEqual([ref.as_tuple() for ref in first], [ref.as_tuple() for ref in second])


class GetQuestionTests(TestCase):
    def test_a_ref_resolves_to_its_row(self) -> None:
        question = make_single_answer()
        ref = selectors.QuestionRef(QuestionType.SINGLE_ANSWER, str(question.id))
        self.assertEqual(selectors.get_question(ref=ref).id, question.id)

    def test_a_deactivated_question_still_resolves(self) -> None:
        """Match history asks for exactly the question that was played, and a
        question retired since is still what happened."""
        question = make_single_answer()
        question.__class__.objects.filter(id=question.id).update(is_active=False)

        ref = selectors.QuestionRef(QuestionType.SINGLE_ANSWER, str(question.id))
        self.assertEqual(selectors.get_question(ref=ref).id, question.id)

    def test_an_unknown_type_or_id_is_not_found(self) -> None:
        question = make_single_answer()
        for ref in (
            selectors.QuestionRef("telepathy", str(question.id)),
            selectors.QuestionRef(QuestionType.SINGLE_ANSWER, "not-a-uuid"),
            selectors.QuestionRef(
                QuestionType.TRUE_FALSE, "00000000-0000-0000-0000-000000000000"
            ),
        ):
            with self.subTest(ref=ref):
                with self.assertRaises(NotFound):
                    selectors.get_question(ref=ref)

    def test_a_slug_is_found_whichever_table_it_lives_in(self) -> None:
        for question_type, factory in QUESTION_FACTORIES.items():
            with self.subTest(question_type):
                factory(slug=f"{question_type}-named")
                found = selectors.question_by_slug(slug=f"{question_type}-named")
                self.assertEqual(found.question_type, question_type)

    def test_an_unknown_slug_is_not_found(self) -> None:
        with self.assertRaises(NotFound):
            selectors.question_by_slug(slug="never-written")


class CatalogDepthTests(TestCase):
    """The read behind ``manage.py questions_report``."""

    def setUp(self) -> None:
        self.category = make_category()

    def test_questions_are_counted_into_the_band_their_level_falls_in(self) -> None:
        stock(category=self.category, levels=[1, 3, 5, 5, 9])

        (depth,) = selectors.catalog_depth()
        self.assertEqual([band.total for band in depth.bands], [2, 2, 1])
        self.assertEqual(depth.total, 5)

    def test_counts_are_broken_down_by_type(self) -> None:
        """A band that is deep overall and holds no ordering questions is a gap,
        not an average."""
        for question_type, factory in QUESTION_FACTORIES.items():
            factory(slug=f"{question_type}-counted", level=2, category=self.category)

        (depth,) = selectors.catalog_depth()
        self.assertEqual(
            depth.by_type, {question_type: 1 for question_type in QUESTION_MODELS}
        )

    def test_only_askable_questions_are_counted(self) -> None:
        stock(category=self.category, levels=[1, 1, 1])
        QUESTION_MODELS[QuestionType.SINGLE_ANSWER].objects.filter(
            slug="q-0"
        ).update(is_active=False)

        (depth,) = selectors.catalog_depth()
        self.assertEqual(depth.total, 2)

    def test_inactive_categories_are_left_out(self) -> None:
        """The report answers "what can be played right now", and a category
        that is switched off is not a gap to fix."""
        stock(category=self.category, levels=[1])
        offseason = make_category(slug="f1", name="F1", is_active=False)
        stock(category=offseason, levels=[1], slug_prefix="f1")

        self.assertEqual(
            [depth.category.slug for depth in selectors.catalog_depth()], ["nba"]
        )
        self.assertEqual(
            [
                depth.category.slug
                for depth in selectors.catalog_depth(
                    categories=[self.category, offseason]
                )
            ],
            ["nba", "f1"],
        )

    def test_a_band_is_playable_once_it_holds_a_matchs_worth(self) -> None:
        stock(category=self.category, levels=[1] * 7)

        (depth,) = selectors.catalog_depth()
        easy, medium, hard = depth.bands
        self.assertTrue(easy.playable())
        self.assertFalse(medium.playable())
        self.assertTrue(medium.playable(count=0))
        self.assertEqual(
            [band.band.name for band in depth.thin_bands()], ["medium", "hard"]
        )

    def test_the_depth_read_is_a_handful_of_queries_not_one_per_band(self) -> None:
        """One grouped query per question type. The report prints three bands and
        seven types; counting them one cell at a time is 21 round trips to draw a
        small table, and it grows with every band anyone adds."""
        stock(category=self.category, levels=[1, 4, 8])

        with self.assertNumQueries(len(QUESTION_MODELS) + 1):
            selectors.catalog_depth()
