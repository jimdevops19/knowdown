"""The four cases ``plan.md`` step 11 names, each encoded and each reaching a
terminal state with no scheduled work left pointing at it."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core_common.exceptions import Conflict
from apps.matches import selectors, services
from apps.matches.constants import QUESTION_TIME_LIMIT_MS
from apps.matches.models import Matchup
from apps.matches.tests.factories import make_matchup
from apps.questions.selectors import QuestionRef, get_question


def _resolve(matchup_question):
    return get_question(
        ref=QuestionRef(matchup_question.question_type, matchup_question.question_id)
    )


class UnansweredQuestionTests(TestCase):
    def test_a_question_nobody_answers_closes_once_the_limit_passes(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        question = selectors.get_matchup_question(matchup=matchup, order=1)

        # Nobody has answered, and time has not run out — closing it now would
        # let a client race the opponent's clock.
        with self.assertRaises(Conflict):
            services.complete_question(matchup=matchup, order=1)

        question.started_at = timezone.now() - timedelta(
            milliseconds=QUESTION_TIME_LIMIT_MS + 1
        )
        question.save(update_fields=["started_at"])

        services.complete_question(matchup=matchup, order=1)
        question.refresh_from_db()
        self.assertIsNotNone(question.completed_at)
        for side in matchup.players.all():
            self.assertEqual(side.score, 0)
            self.assertEqual(side.correct_answers, 0)


class LateAndDuplicateSubmissionTests(TestCase):
    def test_an_answer_after_the_question_has_already_closed_is_refused(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        question = selectors.get_matchup_question(matchup=matchup, order=1)
        concrete = _resolve(question)
        player_one, player_two = (side.player for side in matchup.players.all())

        services.submit_answer(
            matchup=matchup,
            player=player_one,
            order=1,
            payload={"type": "single-answer", "option_id": concrete.options.first().id},
        )
        services.submit_answer(
            matchup=matchup,
            player=player_two,
            order=1,
            payload={"type": "single-answer", "option_id": concrete.options.first().id},
        )
        question.refresh_from_db()
        self.assertIsNotNone(question.completed_at)  # both answered — closed already

        third_player_matchup = make_matchup(question_count=3)  # a fresh matchup+question
        services.start_matchup(matchup=third_player_matchup)
        late_question = selectors.get_matchup_question(matchup=third_player_matchup, order=1)
        late_question.completed_at = timezone.now()
        late_question.save(update_fields=["completed_at"])
        late_player = third_player_matchup.players.first().player
        late_concrete = _resolve(late_question)

        with self.assertRaises(Conflict):
            services.submit_answer(
                matchup=third_player_matchup,
                player=late_player,
                order=1,
                payload={
                    "type": "single-answer",
                    "option_id": late_concrete.options.first().id,
                },
            )

    def test_a_retried_submission_is_idempotent_not_double_scored(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        question = selectors.get_matchup_question(matchup=matchup, order=1)
        concrete = _resolve(question)
        player = matchup.players.first().player
        payload = {
            "type": "single-answer",
            "option_id": concrete.options.get(is_correct=True).id,
        }

        first = services.submit_answer(matchup=matchup, player=player, order=1, payload=payload)
        second = services.submit_answer(matchup=matchup, player=player, order=1, payload=payload)

        self.assertEqual(first.pk, second.pk)
        side = selectors.get_matchup_player(matchup=matchup, player=player)
        self.assertEqual(side.correct_answers, 1)  # not 2


class AbandonmentTests(TestCase):
    def test_a_player_who_leaves_mid_match_hands_the_win_to_the_other(self):
        matchup = make_matchup(question_count=5)
        services.start_matchup(matchup=matchup)
        leaver, stayer = (side.player for side in matchup.players.all())

        services.abandon_matchup(matchup=matchup, leaving_player=leaver)

        matchup.refresh_from_db()
        self.assertEqual(matchup.status, Matchup.Status.COMPLETED)
        self.assertEqual(matchup.outcome, Matchup.Outcome.ABANDONED)
        self.assertIsNotNone(matchup.completed_at)

        leaver_side = selectors.get_matchup_player(matchup=matchup, player=leaver)
        stayer_side = selectors.get_matchup_player(matchup=matchup, player=stayer)
        self.assertFalse(leaver_side.is_winner)
        self.assertTrue(stayer_side.is_winner)
        self.assertIsNotNone(leaver_side.left_at)

        # No scheduled work left pointing at it: the question in progress
        # never closes, and nothing advances past it.
        self.assertIsNone(selectors.current_question(matchup=matchup))

    def test_abandoning_twice_is_idempotent(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        leaver = matchup.players.first().player

        services.abandon_matchup(matchup=matchup, leaving_player=leaver)
        services.abandon_matchup(matchup=matchup, leaving_player=leaver)  # must not raise

    def test_a_finished_matchup_cannot_be_abandoned(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        services.complete_matchup(matchup=matchup)
        leaver = matchup.players.first().player

        with self.assertRaises(Conflict):
            services.abandon_matchup(matchup=matchup, leaving_player=leaver)
