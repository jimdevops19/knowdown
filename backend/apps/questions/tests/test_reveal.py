"""The other side of the anti-cheat suite: what a *finished* question may say.

``test_serializers`` proves the play-time payload is silent. This one proves the
reveal is not — and, more importantly, that the two are still separate things:

1. **Every type can be explained.** The fifth sibling registry is complete, so a
   box score cannot meet a question it can show and cannot answer.
2. **A long pool is cut before it is serialized.** The names past
   ``POOL_REVEAL_LIMIT`` must not be in the payload at all. "The client only
   renders five" is not a mechanism — the other three hundred would be sitting
   in the response body, which is the same leak with a nicer screen in front of
   it.
3. **The player's own answer survives the cut.** A pool truncated blind would
   tell a player who was right that five other things were right instead.
4. **The boundary did not move.** The reveal module is not swept into the
   play-time suite by accident, and the play-time payload for the same question
   still names nothing.
"""

from __future__ import annotations

from django.test import TestCase

from apps.questions.api.reveal import (
    ANSWER_KEY_BUILDERS,
    POOL_REVEAL_LIMIT,
    serialize_answer_key,
)
from apps.questions.api.serializers import serialize_for_play
from apps.questions.models import QUESTION_MODELS, MatrixCellAnswer
from apps.questions.rosters import load_rosters

from .factories import (
    QUESTION_FACTORIES,
    make_free_text,
    make_matrix,
    make_multiple_answer,
    make_ordering,
    make_single_answer,
    make_team_matrix,
    make_true_false,
)
from .test_serializers import MATCHUP, flatten


class RegistryTests(TestCase):
    def test_every_question_type_can_be_revealed(self) -> None:
        """A type that can be drawn and not explained is a box score with a hole
        in it — and, since the builder is looked up at render time, one that
        raises rather than degrades."""
        self.assertEqual(set(ANSWER_KEY_BUILDERS), set(QUESTION_MODELS))

    def test_every_type_reveals_something_naming_its_own_type(self) -> None:
        for question_type, factory in QUESTION_FACTORIES.items():
            with self.subTest(type=question_type):
                key = serialize_answer_key(question=factory(slug=f"q-{question_type}"))
                self.assertEqual(key["type"], question_type)
                self.assertGreater(len(key), 1, "a key with only a type says nothing")


class WhatIsRevealedTests(TestCase):
    def test_a_single_answer_reveals_the_correct_option_id(self) -> None:
        question = make_single_answer()
        correct = question.options.get(is_correct=True)

        key = serialize_answer_key(question=question)

        self.assertEqual(key["option_ids"], [correct.id])

    def test_a_multiple_answer_reveals_every_correct_option_id(self) -> None:
        question = make_multiple_answer()
        correct = {option.id for option in question.options.filter(is_correct=True)}

        key = serialize_answer_key(question=question)

        self.assertEqual(set(key["option_ids"]), correct)
        self.assertGreater(len(correct), 1, "the factory should build a real set")

    def test_a_true_false_reveals_its_boolean(self) -> None:
        question = make_true_false(answer=False)
        self.assertIs(serialize_answer_key(question=question)["answer"], False)

    def test_an_ordering_reveals_the_authored_arrangement(self) -> None:
        """The play-time board is shuffled and this one must not be — the order
        *is* the answer, so a reveal that shuffled would reveal nothing."""
        question = make_ordering(items=("1991", "1992", "1993", "1996", "1998"))
        authored = [
            option.id for option in question.options.order_by("correct_position")
        ]

        self.assertEqual(serialize_answer_key(question=question)["option_ids"], authored)

    def test_a_matrix_reveals_a_pool_per_asked_cell(self) -> None:
        """Per *asked* cell: the sparse intersections are not answers withheld,
        they are squares the question never asked about."""
        question = make_matrix()

        cells = serialize_answer_key(question=question)["cells"]

        self.assertEqual(len(cells), question.cells.count())
        for cell in cells:
            self.assertTrue(cell["accepted"], "an asked cell with no answer")
            self.assertEqual(cell["total"], len(cell["accepted"]))


class TruncationTests(TestCase):
    """Layer 2: the tail does not leave the process."""

    def _grid_with_a_long_pool(self, size: int):
        question = make_matrix(cells=(("Bulls", "1990s", "1996"),))
        cell = question.cells.get()
        cell.answers.all().delete()
        for index in range(size):
            MatrixCellAnswer.objects.create(
                cell=cell, value=f"Player {index:03d}", probability_score=2
            )
        return question, cell

    def test_a_long_pool_is_cut_to_the_limit(self) -> None:
        question, _ = self._grid_with_a_long_pool(22)

        cell = serialize_answer_key(question=question)["cells"][0]

        self.assertEqual(len(cell["accepted"]), POOL_REVEAL_LIMIT)
        self.assertEqual(cell["total"], 22)

    def test_the_hidden_tail_is_nowhere_in_the_payload(self) -> None:
        """The point of the whole exercise. A client showing "… and 17 more"
        over a response body containing all 22 has published 22."""
        question, cell = self._grid_with_a_long_pool(22)
        every_value = [answer.value for answer in cell.answers.all()]

        key = serialize_answer_key(question=question)
        _, values = flatten(key)

        shown = key["cells"][0]["accepted"]
        withheld = [value for value in every_value if value not in shown]
        self.assertEqual(len(withheld), 17)
        for value in withheld:
            self.assertNotIn(value, values)

    def test_a_free_text_pool_is_cut_the_same_way(self) -> None:
        question = make_free_text(
            accepted=("Kobe Bryant", "Kobe", "Bryant", "Black Mamba", "Mamba", "KB24")
        )

        key = serialize_answer_key(question=question)

        self.assertEqual(len(key["accepted"]), POOL_REVEAL_LIMIT)
        self.assertEqual(key["total"], 6)


class PreferredAnswerTests(TestCase):
    """Layer 3: what the player said comes first, when what they said was right."""

    def test_the_players_own_answer_leads_a_truncated_pool(self) -> None:
        question = make_free_text(
            accepted=("Kobe Bryant", "Kobe", "Bryant", "Black Mamba", "Mamba", "KB24")
        )

        key = serialize_answer_key(
            question=question, submitted={"type": "free-text", "text": "KB24"}
        )

        self.assertEqual(key["accepted"][0], "KB24")
        self.assertEqual(len(key["accepted"]), POOL_REVEAL_LIMIT)

    def test_it_is_matched_the_way_the_evaluator_matches_it(self) -> None:
        """Folded, not compared raw — a player who typed ``  kobe   BRYANT``
        was right, and a reveal that put somebody else's spelling first would be
        disagreeing with the score it is printed beside."""
        question = make_free_text(
            accepted=("Kobe Bryant", "Kobe", "Bryant", "Black Mamba", "Mamba", "KB24")
        )

        key = serialize_answer_key(
            question=question,
            submitted={"type": "free-text", "text": "  kobe   BRYANT "},
        )

        self.assertEqual(key["accepted"][0], "Kobe Bryant")

    def test_a_wrong_answer_changes_nothing(self) -> None:
        question = make_free_text(accepted=("Kobe Bryant", "Kobe"))

        unordered = serialize_answer_key(question=question)
        wrong = serialize_answer_key(
            question=question, submitted={"type": "free-text", "text": "Shaq"}
        )

        self.assertEqual(wrong, unordered)

    def test_a_matrix_floats_each_cell_the_player_got_right(self) -> None:
        question = make_matrix()
        cell = question.cells.get(row__title="Lakers", column__title="2000s")

        key = serialize_answer_key(
            question=question,
            submitted={
                "type": "matrix",
                "cells": [
                    {"row_id": cell.row_id, "column_id": cell.column_id, "answer": "2002"}
                ],
            },
        )

        revealed = next(
            entry
            for entry in key["cells"]
            if (entry["row_id"], entry["column_id"]) == (cell.row_id, cell.column_id)
        )
        self.assertEqual(revealed["accepted"][0], "2002")


class PoolOrderingTests(TestCase):
    """Layer 3b: a cut pool keeps the *obvious* names, not an arbitrary five.

    Both kinds of grid order by ``probability_score`` — the authored one by
    ``MatrixCellAnswer.Meta.ordering``, the team one explicitly — and the reason
    is the truncation above: whichever five survive are the five the reveal is,
    so they had better be the five a person would actually have thought of
    rather than whichever rows the database handed back first.
    """

    def test_an_authored_cell_reveals_its_most_obvious_answers_first(self) -> None:
        question = make_matrix(
            cells=(
                (
                    "Bulls",
                    "1990s",
                    (("Deep cut", 9), ("Everybody says it", 2), ("Middling", 5)),
                ),
            )
        )

        cell = serialize_answer_key(question=question)["cells"][0]

        self.assertEqual(
            cell["accepted"], ["Everybody says it", "Middling", "Deep cut"]
        )

    def test_a_team_cell_reveals_its_most_obvious_players_first(self) -> None:
        """The roster path has no ``Meta.ordering`` to inherit — the names come
        out of ``rosters``, so the sort is the module's own and this is what
        holds it."""
        question = make_team_matrix()
        rosters = load_rosters()

        for cell in question.cells.select_related("row", "column").all():
            with self.subTest(cell=f"{cell.row.title} x {cell.column.title}"):
                players = {
                    rosters.player(player_id).name: rosters.player(player_id)
                    for player_id in rosters.players_for_all(
                        [cell.row.title, cell.column.title]
                    )
                }
                revealed = next(
                    entry
                    for entry in serialize_answer_key(question=question)["cells"]
                    if (entry["row_id"], entry["column_id"])
                    == (cell.row_id, cell.column_id)
                )
                shown = [players[name] for name in revealed["accepted"]]
                self.assertEqual(len(shown), POOL_REVEAL_LIMIT)

                scores = [player.probability_score for player in shown]
                self.assertEqual(scores, sorted(scores), "obvious names first")

                withheld = [
                    player for name, player in players.items()
                    if name not in revealed["accepted"]
                ]
                self.assertLessEqual(
                    max(scores),
                    min(player.probability_score for player in withheld),
                    "a deeper cut survived the truncation than one that did not",
                )


class BoundaryTests(TestCase):
    """Layer 4: the reveal module is a module apart, and stayed that way."""

    def test_the_reveal_module_is_not_swept_into_the_play_time_suite(self) -> None:
        """``test_serializers.every_play_serializer`` filters on ``__module__``.
        If the reveal ever moves into ``api.serializers``, that suite starts
        failing on it — which is the intended alarm, and this test is the note
        saying so rather than a second alarm."""
        from apps.questions.api import reveal, serializers as play

        self.assertNotEqual(reveal.__name__, play.__name__)

    def test_revealing_a_question_does_not_change_what_its_board_says(self) -> None:
        """The two payloads are built from the same row, and only one of them
        may name an answer.

        The board carries the correct option's *id* and always has — every
        option's id is on it, which is how a submission names one. What it does
        not carry is anything saying **which** of them is right, and that is the
        difference the reveal makes: same ids, one of them singled out.
        """
        question = make_single_answer()
        correct = question.options.get(is_correct=True)

        board = serialize_for_play(question=question, matchup_id=MATCHUP)
        board_keys, _ = flatten(board)

        self.assertNotIn("is_correct", board_keys)
        self.assertNotIn("option_ids", board_keys)
        self.assertEqual(
            serialize_answer_key(question=question)["option_ids"], [correct.id]
        )
