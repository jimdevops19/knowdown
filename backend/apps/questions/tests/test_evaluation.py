"""What counts as right, what counts as wrong, and what counts as a bug.

The three-way split is the point of this suite. A payload is either a correct
answer, an incorrect answer, or **not an answer at all**, and the third case
raises rather than scoring zero — because a client sending nonsense is a bug,
and a server that quietly scores it zero is a server where that bug lives
forever. Every question type is put through all three, table-driven off the
registry, so a new answer shape cannot join the platform with only its happy
path covered.
"""

from __future__ import annotations

from django.test import TestCase

from apps.core_common.exceptions import ValidationFailed
from apps.questions.models import QUESTION_MODELS, MatrixCellAnswer, QuestionType
from apps.questions.schemas.answers import ANSWER_SUBMISSIONS
from apps.questions.services.evaluation import ANSWER_EVALUATORS, evaluate_answer

from .factories import (
    QUESTION_FACTORIES,
    make_free_text,
    make_matrix,
    make_team_matrix,
    make_multiple_answer,
    make_ordering,
    make_single_answer,
)

#: An id no option has. Deliberately not "one past the last" — that races with
#: the sequence — but far beyond anything a test creates.
ABSENT_OPTION_ID = 10**9


def correct_option(question):
    return question.options.get(is_correct=True)


def wrong_option(question):
    return question.options.filter(is_correct=False).first()


def ordered_ids(question) -> list[int]:
    return [option.id for option in question.options.order_by("correct_position")]


def cell_payload(question, *titles_and_answers) -> dict:
    """A matrix payload naming its cells by heading title, for readability.

    The wire format is ids; the test writes titles and this resolves them, so a
    case reads as "Bulls in the 1990s, and they got it right".
    """
    rows = {row.title: row.id for row in question.rows.all()}
    columns = {column.title: column.id for column in question.columns.all()}
    return {
        "type": QuestionType.MATRIX,
        "cells": [
            {"row_id": rows[row], "column_id": columns[column], "answer": answer}
            for row, column, answer in titles_and_answers
        ],
    }


#: One right, one wrong and one malformed payload per question type.
#:
#: Each is a callable taking the question, because every payload but true/false's
#: names an id that does not exist until the row does. The *malformed* entry is
#: chosen to be a different kind of malformed per type, so the suite covers
#: several ways a client can be wrong rather than seven copies of one: an id
#: nobody has, an id belonging elsewhere, an empty string, a bad literal, an
#: incomplete permutation, an unasked intersection.
CASES: dict[str, dict] = {
    QuestionType.SINGLE_ANSWER: {
        "right": lambda q: {"type": q.question_type, "option_id": correct_option(q).id},
        "wrong": lambda q: {"type": q.question_type, "option_id": wrong_option(q).id},
        # An id no option has at all.
        "malformed": lambda q: {"type": q.question_type, "option_id": ABSENT_OPTION_ID},
    },
    QuestionType.IMAGE_ANSWER: {
        "right": lambda q: {"type": q.question_type, "option_id": correct_option(q).id},
        "wrong": lambda q: {"type": q.question_type, "option_id": wrong_option(q).id},
        # Zero is not a BigAutoField value, so the schema refuses it unaided.
        "malformed": lambda q: {"type": q.question_type, "option_id": 0},
    },
    QuestionType.MULTIPLE_ANSWER: {
        "right": lambda q: {
            "type": q.question_type,
            "option_ids": [o.id for o in q.options.filter(is_correct=True)],
        },
        # One right and one wrong: an answer, and not the right one.
        "wrong": lambda q: {
            "type": q.question_type,
            "option_ids": [
                q.options.filter(is_correct=True).first().id,
                q.options.filter(is_correct=False).first().id,
            ],
        },
        "malformed": lambda q: {
            "type": q.question_type,
            "option_ids": [correct_option_ids(q)[0], ABSENT_OPTION_ID],
        },
    },
    QuestionType.TRUE_FALSE: {
        "right": lambda q: {"type": q.question_type, "answer": q.answer},
        "wrong": lambda q: {"type": q.question_type, "answer": not q.answer},
        "malformed": lambda q: {"type": q.question_type, "answer": "maybe"},
    },
    QuestionType.FREE_TEXT: {
        "right": lambda q: {"type": q.question_type, "text": "Kobe Bryant"},
        "wrong": lambda q: {"type": q.question_type, "text": "Michael Jordan"},
        # Typing nothing is not submitting an answer.
        "malformed": lambda q: {"type": q.question_type, "text": ""},
    },
    QuestionType.ORDERING: {
        "right": lambda q: {"type": q.question_type, "option_ids": ordered_ids(q)},
        "wrong": lambda q: {
            "type": q.question_type,
            "option_ids": list(reversed(ordered_ids(q))),
        },
        # An arrangement of three of its four items is not an arrangement.
        "malformed": lambda q: {"type": q.question_type, "option_ids": ordered_ids(q)[:-1]},
    },
    QuestionType.MATRIX: {
        "right": lambda q: cell_payload(
            q,
            ("Bulls", "1990s", "1996"),
            ("Lakers", "2000s", "2001"),
            ("Lakers", "1990s", "1988"),
        ),
        "wrong": lambda q: cell_payload(
            q,
            ("Bulls", "1990s", "1776"),
            ("Lakers", "2000s", "1776"),
            ("Lakers", "1990s", "1776"),
        ),
        # The one intersection the question does not author.
        "malformed": lambda q: cell_payload(q, ("Bulls", "2000s", "1996")),
    },
}


def correct_option_ids(question) -> list[int]:
    return [option.id for option in question.options.filter(is_correct=True)]


class RegistryCoverageTests(TestCase):
    """The three registries and the fixtures are keyed alike, or a question type
    can reach production answering nobody.

    ``models.QUESTION_MODELS`` says a type exists, ``ANSWER_SUBMISSIONS`` says
    what answering it looks like and ``ANSWER_EVALUATORS`` says what counts as
    right. A type in the first and missing from either other is a question the
    platform can *ask* and cannot *score* — which surfaces, without this test, as
    a live match stuck on question three.
    """

    def test_every_question_type_has_a_payload_an_evaluator_and_a_fixture(self) -> None:
        types = set(QUESTION_MODELS)
        self.assertEqual(set(ANSWER_SUBMISSIONS), types)
        self.assertEqual(set(ANSWER_EVALUATORS), types)
        self.assertEqual(set(QUESTION_FACTORIES), types)
        self.assertEqual(set(CASES), types)


class EveryTypeTests(TestCase):
    """Right, wrong and malformed, for all seven shapes."""

    def question_for(self, question_type: str, suffix: str):
        return QUESTION_FACTORIES[question_type](slug=f"{question_type}-{suffix}")

    def test_a_right_answer_is_correct_and_takes_full_credit(self) -> None:
        for question_type, case in CASES.items():
            with self.subTest(question_type):
                question = self.question_for(question_type, "right")
                result = evaluate_answer(
                    question=question, submitted=case["right"](question)
                )
                self.assertTrue(result.is_correct)
                self.assertEqual(result.score, 1.0)

    def test_a_wrong_answer_is_incorrect_and_is_not_an_error(self) -> None:
        """The distinction this suite is built around: being wrong is a normal
        outcome of playing, so it comes back as a verdict and not an exception."""
        for question_type, case in CASES.items():
            with self.subTest(question_type):
                question = self.question_for(question_type, "wrong")
                result = evaluate_answer(
                    question=question, submitted=case["wrong"](question)
                )
                self.assertFalse(result.is_correct)
                self.assertEqual(result.score, 0.0)

    def test_a_malformed_payload_is_refused_rather_than_scored(self) -> None:
        for question_type, case in CASES.items():
            with self.subTest(question_type):
                question = self.question_for(question_type, "malformed")
                with self.assertRaises(ValidationFailed):
                    evaluate_answer(
                        question=question, submitted=case["malformed"](question)
                    )


class MalformedPayloadTests(TestCase):
    """The ways a payload can fail to be an answer, and what the client is told.

    All of these are ``ValidationFailed``, so they land as a 400 through
    ``core_common.exceptions`` — never as a silent zero, and never as a 500.
    """

    def test_an_option_belonging_to_another_question_is_refused(self) -> None:
        """The case a plain "is this id one of ours?" check exists for: a real
        option id, a real question, and no relationship between them."""
        question = make_single_answer(slug="asked")
        other = make_single_answer(slug="not-asked")

        with self.assertRaises(ValidationFailed) as caught:
            evaluate_answer(
                question=question,
                submitted={
                    "type": QuestionType.SINGLE_ANSWER,
                    "option_id": correct_option(other).id,
                },
            )
        self.assertIn("asked", caught.exception.message)

    def test_a_payload_for_a_different_question_type_is_refused(self) -> None:
        """A client answering a question other than the one on its screen."""
        question = make_single_answer(slug="text-question")

        with self.assertRaises(ValidationFailed) as caught:
            evaluate_answer(
                question=question,
                submitted={"type": QuestionType.TRUE_FALSE, "answer": True},
            )
        self.assertIn(QuestionType.SINGLE_ANSWER, caught.exception.message)

    def test_an_unknown_question_type_is_refused(self) -> None:
        question = make_single_answer(slug="known")

        with self.assertRaises(ValidationFailed):
            evaluate_answer(
                question=question, submitted={"type": "telepathy", "option_id": 1}
            )

    def test_an_extra_field_is_refused_rather_than_ignored(self) -> None:
        """Step 10's rule, enforced at the schema: the server measures the
        response time, so a payload offering one is a client to fix, not a field
        to drop on the floor."""
        question = make_single_answer(slug="timed")

        with self.assertRaises(ValidationFailed) as caught:
            evaluate_answer(
                question=question,
                submitted={
                    "type": QuestionType.SINGLE_ANSWER,
                    "option_id": correct_option(question).id,
                    "response_time_ms": 12,
                },
            )
        self.assertIn("response_time_ms", " ".join(caught.exception.details))

    def test_something_that_is_not_an_object_is_refused(self) -> None:
        question = make_single_answer(slug="shapeless")

        for payload in ("single-answer", 7, None, [1, 2]):
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationFailed):
                    evaluate_answer(question=question, submitted=payload)

    def test_the_failure_names_every_problem_at_once(self) -> None:
        """``details`` is a list for the same reason the loader's is: a client
        author fixing a payload wants the whole list, not the first item seven
        times."""
        question = make_single_answer(slug="doubly-wrong")

        with self.assertRaises(ValidationFailed) as caught:
            evaluate_answer(
                question=question,
                submitted={"type": QuestionType.SINGLE_ANSWER, "option": "wrong key"},
            )
        self.assertGreaterEqual(len(caught.exception.details), 2)


class FreeTextTests(TestCase):
    """Comparison is casefolded and whitespace-collapsed on both sides."""

    def setUp(self) -> None:
        self.question = make_free_text(accepted=("Kobe Bryant", "Kobe"))

    def submit(self, text: str):
        return evaluate_answer(
            question=self.question,
            submitted={"type": QuestionType.FREE_TEXT, "text": text},
        )

    def test_case_and_surrounding_space_do_not_matter(self) -> None:
        for text in ("Kobe Bryant", "kobe bryant", "  KOBE BRYANT  ", "kObE  bRyAnT"):
            with self.subTest(text=text):
                self.assertTrue(self.submit(text).is_correct)

    def test_a_shorter_accepted_spelling_counts(self) -> None:
        """Why a question carries several: a player racing a clock types the
        short one."""
        self.assertTrue(self.submit("kobe").is_correct)

    def test_a_different_name_does_not(self) -> None:
        self.assertFalse(self.submit("Michael Jordan").is_correct)

    def test_a_substring_is_not_a_match(self) -> None:
        """Containment would make "Ko" right, and then every free-text question
        is answerable one letter at a time."""
        self.assertFalse(self.submit("Kob").is_correct)


class MultipleAnswerTests(TestCase):
    """All or nothing — the decision recorded in ``services.evaluation``."""

    def setUp(self) -> None:
        self.question = make_multiple_answer()
        self.correct = correct_option_ids(self.question)
        self.incorrect = [
            option.id for option in self.question.options.filter(is_correct=False)
        ]

    def submit(self, option_ids):
        return evaluate_answer(
            question=self.question,
            submitted={
                "type": QuestionType.MULTIPLE_ANSWER,
                "option_ids": list(option_ids),
            },
        )

    def test_the_exact_set_is_correct_whatever_order_it_arrives_in(self) -> None:
        self.assertTrue(self.submit(reversed(self.correct)).is_correct)

    def test_a_subset_scores_nothing(self) -> None:
        result = self.submit(self.correct[:1])
        self.assertFalse(result.is_correct)
        self.assertEqual(result.score, 0.0)

    def test_selecting_everything_scores_nothing(self) -> None:
        """The reason there is no per-option credit: with it, the shotgun is a
        strategy rather than a mistake."""
        result = self.submit(self.correct + self.incorrect)
        self.assertFalse(result.is_correct)
        self.assertEqual(result.score, 0.0)

    def test_repeating_an_option_is_malformed(self) -> None:
        with self.assertRaises(ValidationFailed):
            self.submit([self.correct[0], self.correct[0]])


class OrderingTests(TestCase):
    def setUp(self) -> None:
        self.question = make_ordering(items=("1991", "1992", "1993", "1996"))

    def submit(self, option_ids):
        return evaluate_answer(
            question=self.question,
            submitted={"type": QuestionType.ORDERING, "option_ids": list(option_ids)},
        )

    def test_the_authored_order_is_correct(self) -> None:
        self.assertTrue(self.submit(ordered_ids(self.question)).is_correct)

    def test_one_swapped_pair_scores_nothing(self) -> None:
        """No partial credit: half an ordering is not half an answer, it is a
        different arrangement."""
        ids = ordered_ids(self.question)
        ids[0], ids[1] = ids[1], ids[0]
        result = self.submit(ids)
        self.assertFalse(result.is_correct)
        self.assertEqual(result.score, 0.0)

    def test_an_incomplete_arrangement_is_malformed(self) -> None:
        with self.assertRaises(ValidationFailed) as caught:
            self.submit(ordered_ids(self.question)[:2])
        self.assertIn("exactly once", caught.exception.message)

    def test_an_arrangement_including_a_foreign_item_is_malformed(self) -> None:
        other = make_ordering(slug="another")
        ids = ordered_ids(self.question)[:-1] + [ordered_ids(other)[0]]
        with self.assertRaises(ValidationFailed):
            self.submit(ids)


class MatrixTests(TestCase):
    """Per-cell credit, and what the denominator is.

    The fixture grid is 2x2 with **three** authored cells, so these tests can
    tell ``correct / authored`` apart from ``correct / (rows x columns)`` — and
    can put an answer in the intersection nobody asked about.
    """

    def setUp(self) -> None:
        self.question = make_matrix()

    def submit(self, *cells):
        return evaluate_answer(
            question=self.question, submitted=cell_payload(self.question, *cells)
        )

    def test_every_cell_right_is_a_correct_answer(self) -> None:
        result = self.submit(
            ("Bulls", "1990s", "1996"),
            ("Lakers", "2000s", "2001"),
            ("Lakers", "1990s", "1988"),
        )
        self.assertTrue(result.is_correct)
        self.assertEqual(result.score, 1.0)

    def test_two_cells_of_three_takes_two_thirds_of_the_credit(self) -> None:
        result = self.submit(
            ("Bulls", "1990s", "1996"),
            ("Lakers", "2000s", "2001"),
            ("Lakers", "1990s", "1999"),
        )
        self.assertAlmostEqual(result.score, 2 / 3)

    def test_partial_credit_is_not_a_correct_answer(self) -> None:
        """``is_correct`` is full credit, not any credit — it is the flag a
        scoreboard puts a tick beside."""
        result = self.submit(
            ("Bulls", "1990s", "1996"),
            ("Lakers", "2000s", "2001"),
            ("Lakers", "1990s", "1999"),
        )
        self.assertFalse(result.is_correct)

    def test_a_cell_left_blank_is_wrong_and_not_malformed(self) -> None:
        """A player out of time submits what they filled in. Missing is not
        broken — it scores nothing for that cell."""
        result = self.submit(("Bulls", "1990s", "1996"))
        self.assertAlmostEqual(result.score, 1 / 3)
        self.assertFalse(result.is_correct)

    def test_any_of_a_cells_answers_takes_the_cell(self) -> None:
        """The Lakers/2000s cell accepts 2001 *or* 2002 — the whole point of a
        grid asking "name a player who played for both": there are several right
        answers and a player only has to reach one of them."""
        result = self.submit(
            ("Bulls", "1990s", "1996"),
            ("Lakers", "2000s", "2002"),
            ("Lakers", "1990s", "1988"),
        )
        self.assertTrue(result.is_correct)

    def test_a_rarer_answer_is_worth_exactly_what_the_obvious_one_is(self) -> None:
        """``probability_score`` grades how obscure a pick is and deliberately
        does not pay for it: credit is the fraction of the grid filled
        correctly, so two players who both filled it in score the same."""
        question = make_matrix(
            slug="graded",
            cells=(("Bulls", "1990s", (("1996", 2), ("1998", 10))),),
        )
        obvious = evaluate_answer(
            question=question, submitted=cell_payload(question, ("Bulls", "1990s", "1996"))
        )
        deep_cut = evaluate_answer(
            question=question, submitted=cell_payload(question, ("Bulls", "1990s", "1998"))
        )
        self.assertEqual(obvious, deep_cut)
        self.assertTrue(obvious.is_correct)

    def test_a_cell_with_several_answers_is_still_one_cell_of_credit(self) -> None:
        """Two answers at one intersection are two ways to fill one square, not
        two squares — the denominator is cells, and a grid whose first cell
        accepts three names is not worth more than one whose first cell accepts
        one."""
        result = self.submit(("Lakers", "2000s", "2002"))
        self.assertAlmostEqual(result.score, 1 / 3)

    def test_cell_answers_are_compared_the_way_free_text_is(self) -> None:
        result = self.submit(
            ("Bulls", "1990s", " 1996 "),
            ("Lakers", "2000s", "2001"),
            ("Lakers", "1990s", "1988"),
        )
        self.assertTrue(result.is_correct)

    def test_answering_an_intersection_nobody_asked_about_is_malformed(self) -> None:
        """The difference between not knowing an answer and answering a question
        that was not put."""
        with self.assertRaises(ValidationFailed) as caught:
            self.submit(("Bulls", "2000s", "1996"))
        self.assertIn("not a cell it asks for", caught.exception.message)

    def test_two_answers_for_one_intersection_is_malformed(self) -> None:
        with self.assertRaises(ValidationFailed):
            self.submit(("Bulls", "1990s", "1996"), ("Bulls", "1990s", "1997"))

    def test_a_heading_from_another_grid_is_malformed(self) -> None:
        other = make_matrix(slug="another-grid")
        payload = cell_payload(other, ("Bulls", "1990s", "1996"))
        with self.assertRaises(ValidationFailed):
            evaluate_answer(question=self.question, submitted=payload)


class TeamMatrixTests(TestCase):
    """``kind: teams`` — the same grid, scored against the roster artifact.

    Every rule ``MatrixTests`` pins down still holds; what changes is only where
    "is this cell right?" is answered, so these cases are about the seam rather
    than about credit arithmetic a second time.

    The fixture is a 2x2 of well-travelled franchises with one intersection left
    out, which is what makes it possible to answer a square nobody asked about.
    """

    def setUp(self) -> None:
        self.question = make_team_matrix(
            rows=("Chicago Bulls", "Boston Celtics"),
            columns=("Los Angeles Lakers", "Miami Heat"),
            cells=(
                ("Chicago Bulls", "Los Angeles Lakers"),
                ("Boston Celtics", "Los Angeles Lakers"),
                ("Boston Celtics", "Miami Heat"),
            ),
        )

    def submit(self, *cells):
        return evaluate_answer(
            question=self.question, submitted=cell_payload(self.question, *cells)
        )

    def test_a_player_of_both_franchises_takes_the_cell(self) -> None:
        result = self.submit(("Chicago Bulls", "Los Angeles Lakers", "Dennis Rodman"))
        self.assertAlmostEqual(result.score, 1 / 3)

    def test_a_player_of_neither_takes_nothing(self) -> None:
        self.assertEqual(
            self.submit(("Chicago Bulls", "Los Angeles Lakers", "Nobody At All")).score,
            0.0,
        )

    def test_a_player_of_only_one_of_them_takes_nothing(self) -> None:
        """The cell asks for both shirts, not for a name either franchise
        recognises. Michael Jordan is as famous as a wrong answer gets here."""
        self.assertEqual(
            self.submit(("Boston Celtics", "Miami Heat", "Michael Jordan")).score, 0.0
        )

    def test_the_whole_grid_right_is_a_correct_answer(self) -> None:
        result = self.submit(
            ("Chicago Bulls", "Los Angeles Lakers", "Dennis Rodman"),
            ("Boston Celtics", "Los Angeles Lakers", "Rajon Rondo"),
            ("Boston Celtics", "Miami Heat", "Ray Allen"),
        )
        self.assertTrue(result.is_correct)
        self.assertEqual(result.score, 1.0)

    def test_names_are_compared_the_way_every_typed_answer_is(self) -> None:
        self.assertAlmostEqual(
            self.submit(
                ("Chicago Bulls", "Los Angeles Lakers", "  dennis   RODMAN ")
            ).score,
            1 / 3,
        )

    def test_the_denominator_is_the_cells_the_loader_wrote(self) -> None:
        """Three cells of a 2x2, so credit is thirds — the sparseness of a
        derived grid is decided by the artifact rather than by an author, and it
        is still the denominator."""
        self.assertAlmostEqual(
            self.submit(
                ("Chicago Bulls", "Los Angeles Lakers", "Dennis Rodman"),
                ("Boston Celtics", "Los Angeles Lakers", "Rajon Rondo"),
            ).score,
            2 / 3,
        )

    def test_answering_an_intersection_nobody_asked_about_is_malformed(self) -> None:
        with self.assertRaises(ValidationFailed) as caught:
            self.submit(("Chicago Bulls", "Miami Heat", "Dwyane Wade"))
        self.assertIn("not a cell it asks for", caught.exception.message)

    def test_a_grid_with_no_cells_is_refused_rather_than_divided_by_zero(self) -> None:
        empty = make_team_matrix(slug="empty-team-grid", cells=())
        other = make_team_matrix(slug="a-grid-with-cells")
        payload = cell_payload(
            other, ("Chicago Bulls", "Washington Wizards", "Michael Jordan")
        )
        with self.assertRaises(ValidationFailed):
            evaluate_answer(question=empty, submitted=payload)

    def test_it_stores_no_answers_of_its_own(self) -> None:
        """The point of the kind: the answer key is the artifact, so a question
        that asks about the Lakers does not carry its own copy of the Lakers."""
        self.assertEqual(
            MatrixCellAnswer.objects.filter(cell__question=self.question).count(), 0
        )
