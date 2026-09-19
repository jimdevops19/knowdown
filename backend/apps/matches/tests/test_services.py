"""The whole game, through services alone — no consumer, no socket
(``backend/CLAUDE.md``'s rule for Phase C)."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core_common.exceptions import Conflict, ValidationFailed
from apps.matches import selectors, services
from apps.matches.constants import (
    FALLBACK_QUESTION_TIME_LIMIT_MS,
    LATE_ANSWER_FLOOR_MS,
    PRE_QUESTION_INFO_MS,
    QUESTION_READ_DELAY_MS,
    SPEED_SCORED_TYPES,
    score_answer,
    time_limit_ms_for,
)
from apps.matches.models import Matchup
from apps.matches.tests.factories import make_matchup, stock_category
from apps.players.tests.factories import make_player
from apps.questions.models import QuestionType
from apps.questions.selectors import QuestionRef
from apps.questions.selectors import get_question as get_concrete_question
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

    def test_the_last_second_of_the_clock_is_all_worth_the_floor(self):
        """Why the end of the curve is flat: the part-credited boards send
        themselves a beat before the whistle, and that lead is network margin
        rather than thinking time (``LATE_ANSWER_FLOOR_MS``)."""
        at_the_wire = score_answer(
            credit=1.0, response_time_ms=FALLBACK_QUESTION_TIME_LIMIT_MS
        )
        auto_submitted = score_answer(
            credit=1.0,
            response_time_ms=FALLBACK_QUESTION_TIME_LIMIT_MS - LATE_ANSWER_FLOOR_MS,
        )
        self.assertEqual(auto_submitted, at_the_wire)

    def test_a_partial_answer_caught_by_the_clock_is_paid_partly(self):
        """The whole point of the auto-submit: two of three right at the wire is
        two thirds of a question at the floor multiplier, not a zero."""
        self.assertEqual(
            score_answer(
                credit=2 / 3,
                response_time_ms=FALLBACK_QUESTION_TIME_LIMIT_MS,
                question_type=QuestionType.MULTIPLE_ANSWER,
            ),
            33,
        )

    def test_a_short_clock_still_has_a_curve(self):
        """The flat end is capped at half the clock, so a question authored with
        a one-second limit is not paid the floor for an instant answer."""
        self.assertEqual(score_answer(credit=1.0, response_time_ms=0, time_limit_ms=1_000), 100)

    def test_partial_credit_scales_the_same_curve(self):
        full = score_answer(credit=1.0, response_time_ms=0)
        half = score_answer(credit=0.5, response_time_ms=0)
        self.assertEqual(half, full // 2)

    def test_every_type_but_one_is_paid_for_speed(self):
        """The registry, not a list of exceptions — see ``SPEED_SCORED_TYPES``."""
        self.assertEqual(
            set(QuestionType.values) - SPEED_SCORED_TYPES,
            {QuestionType.NAME_AS_MANY},
        )

    def test_a_name_as_many_answer_is_worth_the_same_early_or_late(self):
        """Its clock is a budget to spend, not a deadline to beat.

        A question that asks for as many names as you can manage in thirty
        seconds must not pay double for stopping at one second — that would be
        paying players for the one strategy the mode exists to discourage.
        """
        early = score_answer(
            credit=1.0,
            response_time_ms=0,
            time_limit_ms=30_000,
            question_type=QuestionType.NAME_AS_MANY,
        )
        late = score_answer(
            credit=1.0,
            response_time_ms=29_999,
            time_limit_ms=30_000,
            question_type=QuestionType.NAME_AS_MANY,
        )
        self.assertEqual(early, late)
        self.assertEqual(early, 100)

    def test_an_ordinary_type_still_pays_for_speed_when_named(self):
        self.assertGreater(
            score_answer(
                credit=1.0, response_time_ms=0, question_type=QuestionType.FREE_TEXT
            ),
            score_answer(
                credit=1.0,
                response_time_ms=FALLBACK_QUESTION_TIME_LIMIT_MS,
                question_type=QuestionType.FREE_TEXT,
            ),
        )


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

    def test_two_humans_are_ranked(self):
        matchup = make_matchup()
        self.assertTrue(matchup.is_ranked)

    def test_a_bot_on_either_side_is_unranked(self):
        from apps.players.models import Player

        human = make_player(email="ranked-human@example.com")
        bot = make_player(email="ranked-bot@example.com")
        Player.objects.filter(pk=bot.pk).update(is_bot=True)
        bot.refresh_from_db()

        matchup = make_matchup(player_one=human, player_two=bot)
        self.assertFalse(matchup.is_ranked)


class SelectMatchQuestionsTests(TestCase):
    def test_refuses_to_redraw_a_board_already_selected(self):
        matchup = make_matchup(question_count=3)
        with self.assertRaises(Conflict):
            services.select_match_questions(matchup=matchup)


#: What ``matrix.yaml`` sets for every grid it holds, and so what the loader
#: writes onto a grid's row. Spelled out here rather than imported, because the
#: engine has no opinion about it: the point of these tests is that a longer
#: clock arrives from the *row*, whatever the file happens to say today.
_MATRIX_CLOCK_SECONDS = 60


class MatrixTimeLimitTests(TestCase):
    """A grid gets more clock than a glance-and-answer question — several
    sparse, independent cells read off a board take longer to work through than
    one claim — and it gets it the way every clock now arrives: off the row,
    written there by the loader from the file the whole type is authored in."""

    def test_a_row_s_clock_outranks_the_fallback(self):
        self.assertGreater(
            time_limit_ms_for(override_seconds=_MATRIX_CLOCK_SECONDS),
            time_limit_ms_for(),
        )
        self.assertEqual(time_limit_ms_for(), FALLBACK_QUESTION_TIME_LIMIT_MS)

    def test_a_question_with_no_clock_of_its_own_gets_the_fallback(self):
        """Neither the question nor a file named one — the only tier left."""
        self.assertEqual(
            time_limit_ms_for(override_seconds=None), FALLBACK_QUESTION_TIME_LIMIT_MS
        )
        self.assertEqual(time_limit_ms_for(override_seconds=5), 5_000)

    def test_an_answer_past_the_default_limit_but_within_the_matrix_limit_still_counts(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        question = selectors.get_matchup_question(matchup=matchup, order=1)

        matrix = make_matrix(slug="grid-time-limit-test", category=matchup.category)
        matrix.time_limit_seconds = _MATRIX_CLOCK_SECONDS  # as matrix.yaml loads it
        matrix.save(update_fields=["time_limit_seconds"])
        question.question_type = QuestionType.MATRIX
        question.question_id = matrix.id
        question.started_at = timezone.now() - timedelta(
            milliseconds=FALLBACK_QUESTION_TIME_LIMIT_MS + 1
        )
        question.save(update_fields=["question_type", "question_id", "started_at"])

        player_one = matchup.players.first().player
        cell = matrix.cells.first()
        cell_answer = cell.answers.first().value
        answer = services.submit_answer(
            matchup=matchup,
            player=player_one,
            order=1,
            payload={
                "type": "matrix",
                "cells": [
                    {
                        "row_id": cell.row_id,
                        "column_id": cell.column_id,
                        "answer": cell_answer,
                    }
                ],
            },
        )
        self.assertGreater(answer.points, 0)

    def test_an_answer_past_the_matrix_limit_is_refused(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        question = selectors.get_matchup_question(matchup=matchup, order=1)

        matrix = make_matrix(slug="grid-time-limit-test-2", category=matchup.category)
        matrix.time_limit_seconds = _MATRIX_CLOCK_SECONDS  # as matrix.yaml loads it
        matrix.save(update_fields=["time_limit_seconds"])
        question.question_type = QuestionType.MATRIX
        question.question_id = matrix.id
        question.started_at = timezone.now() - timedelta(
            milliseconds=time_limit_ms_for(override_seconds=_MATRIX_CLOCK_SECONDS) + 1
        )
        question.save(update_fields=["question_type", "question_id", "started_at"])

        player_one = matchup.players.first().player
        cell = matrix.cells.first()
        cell_answer = cell.answers.first().value
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
                            "answer": cell_answer,
                        }
                    ],
                },
            )

    def test_a_question_s_own_time_limit_is_honoured_end_to_end(self):
        """A single-answer question authored with ``time_limit_seconds: 1``
        gets one second, not the ordinary ten — the row's own value outranks
        the fallback."""
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


class TaskScreenDelayTests(TestCase):
    """A question that states its task first is dealt earlier.

    The server sends one stamp, not two: ``started_at`` is when the clock
    starts, and for a question carrying a ``pre_question_info`` line it is
    pushed out by the beat that line owns the screen for. Everything measured
    from the stamp — the time-limit check, the deadline, the watchdog, a
    gradual-hints reveal — moves with it, which is why there is nothing else to
    change; and the client re-derives "when the question is revealed" by
    subtracting the ordinary read delay back off it.
    """

    def _started_question(self, *, pre_question_info: str):
        matchup = make_matchup(question_count=3)
        question = selectors.get_matchup_question(matchup=matchup, order=1)
        concrete = get_concrete_question(
            ref=QuestionRef(question.question_type, question.question_id)
        )
        concrete.pre_question_info = pre_question_info
        concrete.save(update_fields=["pre_question_info"])

        matchup.status = Matchup.Status.ACTIVE
        matchup.started_at = timezone.now()
        matchup.save(update_fields=["status", "started_at"])
        before = timezone.now()
        started = services.start_question(matchup=matchup, order=1)
        return before, started

    def test_an_ordinary_question_is_stamped_the_ordinary_delay_out(self) -> None:
        before, question = self._started_question(pre_question_info="")
        delay_ms = (question.started_at - before).total_seconds() * 1000
        self.assertAlmostEqual(delay_ms, QUESTION_READ_DELAY_MS, delta=500)

    def test_a_question_with_a_task_screen_is_stamped_further_out(self) -> None:
        before, question = self._started_question(
            pre_question_info="Click to order from earliest to latest"
        )
        delay_ms = (question.started_at - before).total_seconds() * 1000
        self.assertAlmostEqual(
            delay_ms, QUESTION_READ_DELAY_MS + PRE_QUESTION_INFO_MS, delta=500
        )

    def test_the_reading_beat_is_whole_either_way(self) -> None:
        """The property the design rests on, checked as a difference rather
        than as two numbers: whatever the task screen costs, it is spent
        *before* the beat spent reading the question, never out of it."""
        plain_before, plain = self._started_question(pre_question_info="")
        task_before, task = self._started_question(pre_question_info="Do the thing")
        extra_ms = ((task.started_at - task_before) - (plain.started_at - plain_before))
        self.assertAlmostEqual(
            extra_ms.total_seconds() * 1000, PRE_QUESTION_INFO_MS, delta=500
        )
