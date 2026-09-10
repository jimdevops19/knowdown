"""The whole game, through services alone — no consumer, no socket
(``backend/CLAUDE.md``'s rule for Phase C)."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core_common.exceptions import Conflict, ValidationFailed
from apps.matches import selectors, services
from apps.matches.constants import FALLBACK_QUESTION_TIME_LIMIT_MS, score_answer, time_limit_ms_for
from apps.matches.models import Matchup
from apps.matches.tests.factories import make_matchup, stock_category
from apps.players.tests.factories import make_player
from apps.questions.models import QuestionType
from apps.questions.tests.factories import make_matrix


def _correct_option_id(question) -> int:
    return question.options.get(is_correct=True).id


def _wrong_option_id(question) -> int:
    return question.options.filter(is_correct=False).first().id


class FullMatchTests(TestCase):
    def test_plays_a_five_question_match_to_a_winner(self):
        category = stock_category()
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        matchup = services.create_matchup(
            category=category, player_one=alice, player_two=bob, question_count=5
        )
        self.assertEqual(matchup.status, Matchup.Status.WAITING)
        self.assertEqual(matchup.questions.count(), 5)

        services.start_matchup(matchup=matchup)
        matchup.refresh_from_db()
        self.assertEqual(matchup.status, Matchup.Status.ACTIVE)

        for order in range(1, 6):
            concrete = selectors.get_matchup_question(matchup=matchup, order=order)
            question = _resolve(concrete)
            # Alice always answers correctly; Bob never does — a deterministic
            # winner without needing to pin the RNG.
            services.submit_answer(
                matchup=matchup,
                player=alice,
                order=order,
                payload={"type": "single-answer", "option_id": _correct_option_id(question)},
            )
            services.submit_answer(
                matchup=matchup,
                player=bob,
                order=order,
                payload={"type": "single-answer", "option_id": _wrong_option_id(question)},
            )

        matchup.refresh_from_db()
        self.assertEqual(matchup.status, Matchup.Status.COMPLETED)
        self.assertEqual(matchup.outcome, Matchup.Outcome.PLAYED)

        alice_side = selectors.get_matchup_player(matchup=matchup, player=alice)
        bob_side = selectors.get_matchup_player(matchup=matchup, player=bob)
        self.assertTrue(alice_side.is_winner)
        self.assertFalse(bob_side.is_winner)
        self.assertEqual(alice_side.correct_answers, 5)
        self.assertEqual(bob_side.correct_answers, 0)
        self.assertGreater(alice_side.score, 0)
        self.assertEqual(bob_side.score, 0)


def _resolve(matchup_question):
    from apps.questions.selectors import QuestionRef, get_question

    return get_question(
        ref=QuestionRef(matchup_question.question_type, matchup_question.question_id)
    )


class ScoringTests(TestCase):
    def test_a_wrong_answer_is_worth_nothing_regardless_of_speed(self):
        self.assertEqual(score_answer(credit=0.0, response_time_ms=1), 0)

    def test_a_correct_instant_answer_scores_the_maximum(self):
        self.assertEqual(score_answer(credit=1.0, response_time_ms=0), 100)

    def test_a_correct_last_moment_answer_still_earns_the_floor(self):
        self.assertEqual(
            score_answer(credit=1.0, response_time_ms=FALLBACK_QUESTION_TIME_LIMIT_MS), 50
        )

    def test_partial_credit_scales_the_same_curve(self):
        full = score_answer(credit=1.0, response_time_ms=0)
        half = score_answer(credit=0.5, response_time_ms=0)
        self.assertEqual(half, full // 2)


class ServerAuthoritativeTimingTests(TestCase):
    def test_response_time_is_measured_by_the_server_never_the_client(self):
        matchup = make_matchup(question_count=3)
        player = matchup.players.first().player
        services.start_matchup(matchup=matchup)
        question = selectors.get_matchup_question(matchup=matchup, order=1)

        # Backdate the server's own T0, the only clock this test is allowed to
        # move — the payload below still carries no time field at all.
        question.started_at = timezone.now() - timedelta(seconds=4)
        question.save(update_fields=["started_at"])
        concrete = _resolve(question)

        answer = services.submit_answer(
            matchup=matchup,
            player=player,
            order=1,
            payload={"type": "single-answer", "option_id": _correct_option_id(concrete)},
        )

        self.assertGreaterEqual(answer.response_time_ms, 3900)
        self.assertLessEqual(answer.response_time_ms, FALLBACK_QUESTION_TIME_LIMIT_MS)

    def test_a_payload_that_tries_to_smuggle_a_time_field_is_refused(self):
        matchup = make_matchup(question_count=3)
        player = matchup.players.first().player
        services.start_matchup(matchup=matchup)
        question = selectors.get_matchup_question(matchup=matchup, order=1)
        concrete = _resolve(question)

        with self.assertRaises(ValidationFailed):
            services.submit_answer(
                matchup=matchup,
                player=player,
                order=1,
                payload={
                    "type": "single-answer",
                    "option_id": _correct_option_id(concrete),
                    "response_time_ms": 1,
                },
            )


class CreateMatchupTests(TestCase):
    def test_refuses_to_match_a_player_against_themselves(self):
        category = stock_category()
        player = make_player(email="solo@example.com")
        with self.assertRaises(ValidationFailed):
            services.create_matchup(category=category, player_one=player, player_two=player)

    def test_question_count_must_be_one_of_the_allowed_lengths(self):
        category = stock_category()
        with self.assertRaises(ValidationFailed):
            services.create_matchup(
                category=category,
                player_one=make_player(email="a@example.com"),
                player_two=make_player(email="b@example.com"),
                question_count=4,
            )


class SelectMatchQuestionsTests(TestCase):
    def test_refuses_to_redraw_a_board_already_selected(self):
        matchup = make_matchup(question_count=3)
        with self.assertRaises(Conflict):
            services.select_match_questions(matchup=matchup)


class MatrixTimeLimitTests(TestCase):
    """A matrix question gets more clock than the default
    (``apps.matches.constants.FALLBACK_QUESTION_TIME_LIMITS_MS``) — several sparse,
    independent cells read off a grid take longer to work through than one
    glance-and-answer claim."""

    def test_matrix_is_given_more_time_than_the_default(self):
        self.assertGreater(
            time_limit_ms_for(question_type=QuestionType.MATRIX),
            time_limit_ms_for(question_type=QuestionType.SINGLE_ANSWER),
        )
        self.assertEqual(
            time_limit_ms_for(question_type=QuestionType.SINGLE_ANSWER),
            FALLBACK_QUESTION_TIME_LIMIT_MS,
        )

    def test_a_question_s_own_time_limit_outranks_its_type_s_fallback(self):
        self.assertEqual(
            time_limit_ms_for(question_type=QuestionType.MATRIX, override_seconds=5), 5_000
        )
        self.assertEqual(
            time_limit_ms_for(question_type=QuestionType.SINGLE_ANSWER, override_seconds=5), 5_000
        )

    def test_an_answer_past_the_default_limit_but_within_the_matrix_limit_still_counts(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        question = selectors.get_matchup_question(matchup=matchup, order=1)

        matrix = make_matrix(slug="grid-time-limit-test", category=matchup.category)
        question.question_type = QuestionType.MATRIX
        question.question_id = matrix.id
        question.started_at = timezone.now() - timedelta(
            milliseconds=FALLBACK_QUESTION_TIME_LIMIT_MS + 1
        )
        question.save(update_fields=["question_type", "question_id", "started_at"])

        player_one = matchup.players.first().player
        cell = matrix.cells.first()
        answer = services.submit_answer(
            matchup=matchup,
            player=player_one,
            order=1,
            payload={
                "type": "matrix",
                "cells": [
                    {"row_id": cell.row_id, "column_id": cell.column_id, "answer": cell.answer}
                ],
            },
        )
        self.assertGreater(answer.points, 0)

    def test_an_answer_past_the_matrix_limit_is_refused(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        question = selectors.get_matchup_question(matchup=matchup, order=1)

        matrix = make_matrix(slug="grid-time-limit-test-2", category=matchup.category)
        question.question_type = QuestionType.MATRIX
        question.question_id = matrix.id
        question.started_at = timezone.now() - timedelta(
            milliseconds=time_limit_ms_for(question_type=QuestionType.MATRIX) + 1
        )
        question.save(update_fields=["question_type", "question_id", "started_at"])

        player_one = matchup.players.first().player
        cell = matrix.cells.first()
        with self.assertRaises(Conflict):
            services.submit_answer(
                matchup=matchup,
                player=player_one,
                order=1,
                payload={
                    "type": "matrix",
                    "cells": [
                        {
                            "row_id": cell.row_id,
                            "column_id": cell.column_id,
                            "answer": cell.answer,
                        }
                    ],
                },
            )

    def test_a_question_s_own_time_limit_is_honoured_end_to_end(self):
        """A single-answer question authored with ``time_limit_seconds: 1``
        gets one second, not the type's ten — the row's own value outranks
        every fallback."""
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        question = selectors.get_matchup_question(matchup=matchup, order=1)
        concrete = _resolve(question)
        concrete.time_limit_seconds = 1
        concrete.save(update_fields=["time_limit_seconds"])

        question.started_at = timezone.now() - timedelta(milliseconds=1_500)
        question.save(update_fields=["started_at"])

        player_one = matchup.players.first().player
        with self.assertRaises(Conflict):
            services.submit_answer(
                matchup=matchup,
                player=player_one,
                order=1,
                payload={"type": "single-answer", "option_id": _correct_option_id(concrete)},
            )
