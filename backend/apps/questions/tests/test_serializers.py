"""The anti-cheat suite: what a play-time payload must never contain.

Every other test in this app is about being correct. This one is about being
*silent* — a question payload that carries the answer makes the whole game
pointless, and the failure is invisible from the outside, because a match played
against a client reading the answer key looks exactly like a match against
somebody who knows their basketball.

Three layers, on purpose, because each catches what the others cannot:

1. **The declared fields** of every serializer in the app are walked against
   ``FORBIDDEN_FIELD_NAMES`` — the pattern rpool's ``EmailExposureTests`` uses.
   This catches a field added to a serializer that already exists.
2. **The rendered payload** of every question type is scanned recursively for
   the same names *and* for the answer values themselves. This catches a leak
   that arrives without a matching field name — a method field, a nested
   serializer, an extra dict key.
3. **The mechanism itself** is tested: a serializer declaring a forbidden field
   must fail at class creation. Layers 1 and 2 protect the code that exists;
   this one protects the code somebody writes next year, when nobody is reading
   this file.
"""

from __future__ import annotations

import inspect

from django.test import TestCase
from rest_framework import serializers

from apps.questions.api import serializers as play
from apps.questions.api.serializers import (
    FORBIDDEN_FIELD_NAMES,
    QUESTION_SERIALIZERS,
    serialize_for_play,
    shuffle_seed,
)
from apps.questions.models import (
    QUESTION_MODELS,
    MatrixCellAnswer,
    MatrixKind,
    QuestionType,
)

from .factories import (
    QUESTION_FACTORIES,
    make_free_text,
    make_matrix,
    make_team_matrix,
    make_ordering,
    make_single_answer,
    make_true_false,
)

#: Stands in for a ``Matchup`` id until ``apps.matches`` exists. A string,
#: because that is all :func:`shuffle_seed` needs of it.
MATCHUP = "11111111-1111-1111-1111-111111111111"
OTHER_MATCHUP = "22222222-2222-2222-2222-222222222222"


def every_play_serializer() -> list[type[serializers.Serializer]]:
    """Every serializer class in the play-time module, public or private.

    Private ones included deliberately: ``_ImageOptionSerializer`` is nested
    inside a payload that goes to a player, so being unexported protects nothing.
    """
    return [
        member
        for _, member in inspect.getmembers(play, inspect.isclass)
        if issubclass(member, serializers.Serializer)
        and member.__module__ == play.__name__
    ]


def keys_and_values(payload, keys: list, values: list) -> None:
    """Flatten a rendered payload into every key and every scalar it contains."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.append(key)
            keys_and_values(value, keys, values)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            keys_and_values(item, keys, values)
    else:
        values.append(payload)


def flatten(payload) -> tuple[list, list]:
    keys: list = []
    values: list = []
    keys_and_values(payload, keys, values)
    return keys, values


class RegistryTests(TestCase):
    def test_every_question_type_has_a_play_time_serializer(self) -> None:
        """A type that can be drawn and not shown is a match that stalls."""
        self.assertEqual(set(QUESTION_SERIALIZERS), set(QUESTION_MODELS))


class DeclaredFieldTests(TestCase):
    """Layer 1: no serializer in this app declares a field that names an answer."""

    def test_no_serializer_declares_a_forbidden_field(self) -> None:
        for serializer_class in every_play_serializer():
            for name, field in serializer_class._declared_fields.items():
                with self.subTest(serializer=serializer_class.__name__, field=name):
                    source = getattr(field, "source", None) or ""
                    self.assertNotIn(name, FORBIDDEN_FIELD_NAMES)
                    for part in source.split("."):
                        self.assertNotIn(part, FORBIDDEN_FIELD_NAMES)

    def test_no_serializer_is_derived_from_a_model(self) -> None:
        """A ``ModelSerializer`` grows a field when a model grows a column, so
        the answer to a question type invented next year would be published by
        code nobody edited."""
        for serializer_class in every_play_serializer():
            with self.subTest(serializer=serializer_class.__name__):
                self.assertNotIsInstance(
                    serializer_class(), serializers.ModelSerializer
                )


class RenderedPayloadTests(TestCase):
    """Layer 2: what actually goes over the wire, for all seven shapes."""

    def payload_for(self, question_type: str) -> dict:
        question = QUESTION_FACTORIES[question_type](slug=f"{question_type}-shown")
        return serialize_for_play(question=question, matchup_id=MATCHUP)

    def test_no_payload_carries_a_forbidden_key(self) -> None:
        for question_type in QUESTION_MODELS:
            with self.subTest(question_type):
                keys, _ = flatten(self.payload_for(question_type))
                self.assertEqual(set(keys) & FORBIDDEN_FIELD_NAMES, set())

    def test_every_payload_names_its_type_and_its_question(self) -> None:
        """The client has to know what to draw, and a submission has to name the
        same type back (``schemas.answers``)."""
        for question_type in QUESTION_MODELS:
            with self.subTest(question_type):
                payload = self.payload_for(question_type)
                self.assertEqual(payload["type"], question_type)
                self.assertIn("description", payload)
                self.assertIn("id", payload)

    def test_no_payload_carries_the_question_slug(self) -> None:
        """A slug is authored to be readable, and ``kobe-81-point-game`` is a
        perfectly ordinary slug and a complete answer."""
        for question_type in QUESTION_MODELS:
            with self.subTest(question_type):
                keys, _ = flatten(self.payload_for(question_type))
                self.assertNotIn("slug", keys)

    def test_a_true_false_payload_does_not_say_which(self) -> None:
        """No boolean anywhere in the payload, either spelling of it.

        Compared with ``is`` rather than ``==``: ``True == 1`` in Python, and
        ``level`` is an integer, so an equality check here passes or fails on the
        difficulty of the fixture rather than on the leak.
        """
        for answer in (True, False):
            with self.subTest(answer=answer):
                question = make_true_false(slug=f"claim-{answer}", answer=answer)
                _, values = flatten(
                    serialize_for_play(question=question, matchup_id=MATCHUP)
                )
                self.assertFalse(
                    [value for value in values if value is True or value is False]
                )
                self.assertFalse(
                    {str(value).casefold() for value in values} & {"true", "false"}
                )

    def test_a_free_text_payload_does_not_carry_an_accepted_answer(self) -> None:
        question = make_free_text(accepted=("Kobe Bryant", "Kobe"))
        _, values = flatten(serialize_for_play(question=question, matchup_id=MATCHUP))
        for accepted in ("Kobe Bryant", "Kobe"):
            self.assertNotIn(accepted, values)

    def test_a_matrix_payload_carries_no_cell_answer(self) -> None:
        """Every accepted answer of every cell, not just the first: a cell holds
        several, and a payload that named the obscure ones would hand a player
        the half of the grid worth having."""
        question = make_matrix()
        payload = serialize_for_play(question=question, matchup_id=MATCHUP)
        _, values = flatten(payload)
        answers = MatrixCellAnswer.objects.filter(cell__question=question)
        self.assertTrue(answers.exists())
        for answer in answers.values_list("value", flat=True):
            self.assertNotIn(answer, values)

    def test_a_matrix_payload_carries_no_probability_score(self) -> None:
        """How obscure a cell's answers are is a clue to what they are — a grid
        that says "this square's answers are all 9s" narrows the guess."""
        question = make_matrix(
            cells=(("Bulls", "1990s", (("1996", 9),)), ("Lakers", "2000s", "2001"))
        )
        _, values = flatten(serialize_for_play(question=question, matchup_id=MATCHUP))
        self.assertNotIn(9, values)

    def test_a_team_matrix_payload_names_no_player(self) -> None:
        """A ``kind: teams`` grid keeps its answers in the roster artifact
        rather than in the database, so the leak to check for is a *derived*
        one: the payload must name the franchises it asks about and nobody who
        played for both of them."""
        question = make_team_matrix(
            rows=("Chicago Bulls", "Boston Celtics"),
            columns=("Los Angeles Lakers", "Miami Heat"),
        )
        payload = serialize_for_play(question=question, matchup_id=MATCHUP)
        _, values = flatten(payload)

        self.assertEqual(payload["kind"], MatrixKind.TEAMS)
        self.assertIn("Chicago Bulls", values)
        for player in ("Dennis Rodman", "Ray Allen", "LeBron James"):
            self.assertNotIn(player, values)
        self.assertEqual(
            {(cell["row_id"], cell["column_id"]) for cell in payload["cells"]},
            set(question.cells.values_list("row_id", "column_id")),
        )

    def test_a_matrix_payload_says_which_intersections_to_fill(self) -> None:
        """The grid is sparse, so without this a client draws an input in every
        square and a player spends the clock on squares nobody scores."""
        question = make_matrix()
        payload = serialize_for_play(question=question, matchup_id=MATCHUP)

        self.assertEqual(len(payload["cells"]), question.cells.count())
        self.assertEqual(
            {(cell["row_id"], cell["column_id"]) for cell in payload["cells"]},
            set(question.cells.values_list("row_id", "column_id")),
        )
        self.assertEqual(
            [row["title"] for row in payload["rows"]],
            list(question.rows.values_list("title", flat=True)),
            "headings keep their authored order — they are axes, not options",
        )

    def test_an_options_payload_carries_the_ids_a_submission_needs(self) -> None:
        question = make_single_answer()
        payload = serialize_for_play(question=question, matchup_id=MATCHUP)

        self.assertEqual(
            {option["id"] for option in payload["options"]},
            set(question.options.values_list("id", flat=True)),
        )
        self.assertEqual(
            {tuple(sorted(option)) for option in payload["options"]},
            {("id", "text")},
            "an option is an id and what it says, and nothing else",
        )

    def test_a_multiple_answer_payload_does_not_say_how_many_are_correct(self) -> None:
        """On a four-option question, "two of these are right" halves the search
        space."""
        payload = self.payload_for(QuestionType.MULTIPLE_ANSWER)
        keys, _ = flatten(payload)
        for hint in ("correct_count", "answer_count", "select_count", "required"):
            self.assertNotIn(hint, keys)


class MechanismTests(TestCase):
    """Layer 3: the guard that makes layers 1 and 2 hold for code not yet written.

    Both of these fail at *class creation*, which is import time — so the
    mistake stops the process from booting rather than stopping a match from
    being fair.
    """

    def test_declaring_a_forbidden_field_is_a_type_error(self) -> None:
        with self.assertRaises(TypeError) as caught:

            class Leaky(play._PlaySerializer):
                is_correct = serializers.BooleanField()

        self.assertIn("is_correct", str(caught.exception))

    def test_hiding_a_forbidden_field_behind_a_source_is_a_type_error(self) -> None:
        """The version of the mistake a name check alone would miss."""
        with self.assertRaises(TypeError) as caught:

            class Sneaky(play._PlaySerializer):
                hint = serializers.CharField(source="answer")

        self.assertIn("answer", str(caught.exception))


class ShuffleTests(TestCase):
    """The board is shuffled per matchup, not per player.

    Per *player* would mean the two sides of a race were reading different
    boards; not shuffling at all would mean the authored order — which, in the
    resource files, tends to put the correct option first — was a strategy.
    """

    def setUp(self) -> None:
        self.question = make_single_answer(
            options=(("A", True), ("B", False), ("C", False), ("D", False))
        )

    def board(self, matchup_id: str, question=None) -> list[int]:
        payload = serialize_for_play(
            question=question or self.question, matchup_id=matchup_id
        )
        return [option["id"] for option in payload["options"]]

    def test_both_players_of_a_matchup_see_the_same_board(self) -> None:
        """Two serializations, standing in for the two consumers serving the two
        sides. They agree without coordinating, because the order is a function
        of the ids and nothing else."""
        self.assertEqual(self.board(MATCHUP), self.board(MATCHUP))

    def test_the_board_is_stable_across_repeated_serialization(self) -> None:
        """A reconnecting player gets the board they left, not a reshuffled one
        (step 15's mid-match resume depends on this)."""
        first = self.board(MATCHUP)
        for _ in range(5):
            self.assertEqual(self.board(MATCHUP), first)

    def test_the_board_holds_exactly_the_questions_options(self) -> None:
        """A shuffle that loses or repeats an option is a question with a missing
        answer."""
        self.assertEqual(
            sorted(self.board(MATCHUP)),
            sorted(self.question.options.values_list("id", flat=True)),
        )

    def test_a_different_matchup_can_get_a_different_board(self) -> None:
        """So an option's position is not something to memorise across matches.

        Asserted over several matchups rather than one pair: two random orders of
        four options are the same order one time in twenty-four, and a test that
        flakes at 4% is a test people learn to re-run.
        """
        boards = {
            tuple(self.board(f"matchup-{index}")) for index in range(12)
        }
        self.assertGreater(len(boards), 1)

    def test_two_questions_in_one_matchup_shuffle_independently(self) -> None:
        """The seed carries the question id as well, so a matchup is not one
        permutation applied to every board in it."""
        other = make_single_answer(
            slug="second",
            options=(("A", True), ("B", False), ("C", False), ("D", False)),
        )
        seeds = {
            shuffle_seed(matchup_id=MATCHUP, question_id=self.question.id),
            shuffle_seed(matchup_id=MATCHUP, question_id=other.id),
        }
        self.assertEqual(len(seeds), 2)

    def test_an_ordering_question_is_not_served_in_its_correct_order(self) -> None:
        """The type where the shuffle *is* the anti-cheat: the items are stored
        in their answer order, so serving them unshuffled hands over the solution
        while carefully omitting the field that states it."""
        question = make_ordering(items=("1991", "1992", "1993", "1996", "1998"))
        correct = [
            option.id for option in question.options.order_by("correct_position")
        ]

        served = [
            [
                option["id"]
                for option in serialize_for_play(
                    question=question, matchup_id=f"matchup-{index}"
                )["options"]
            ]
            for index in range(12)
        ]
        self.assertTrue(
            any(board != correct for board in served),
            "every matchup served the items in their correct order",
        )

    def test_a_serializer_used_without_a_matchup_keeps_the_authored_order(self) -> None:
        """The admin and the schema examples have no matchup. They get the
        authored order — which is why ``serialize_for_play`` makes ``matchup_id``
        required, so the play path cannot land here by omission."""
        payload = play.SingleAnswerPlaySerializer(self.question).data
        self.assertEqual(
            [option["id"] for option in payload["options"]],
            list(self.question.options.order_by("order").values_list("id", flat=True)),
        )
