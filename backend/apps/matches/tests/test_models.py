"""The DB-level guarantees: exactly two players, one answer per player per
question — the backstops behind ``services``' own checks."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.matches.models import MatchupPlayer, MatchupQuestion, PlayerAnswer
from apps.matches.tests.factories import make_matchup


class MatchupPlayerConstraintTests(TestCase):
    def test_a_player_cannot_join_the_same_matchup_twice(self):
        matchup = make_matchup(question_count=3)
        existing = matchup.players.first()

        with self.assertRaises(IntegrityError), transaction.atomic():
            MatchupPlayer.objects.create(matchup=matchup, player=existing.player)


class PlayerAnswerConstraintTests(TestCase):
    def test_one_answer_per_player_per_question(self):
        matchup = make_matchup(question_count=3)
        question = matchup.questions.get(order=1)
        player = matchup.players.first().player
        PlayerAnswer.objects.create(
            matchup_question=question,
            player=player,
            answer={"option_id": 1},
            is_correct=True,
            score=1.0,
            points=100,
            response_time_ms=500,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            PlayerAnswer.objects.create(
                matchup_question=question,
                player=player,
                answer={"option_id": 2},
                is_correct=False,
                score=0.0,
                points=0,
                response_time_ms=900,
            )


class MatchupQuestionConstraintTests(TestCase):
    def test_a_matchup_cannot_repeat_a_question(self):
        matchup = make_matchup(question_count=3)
        first = matchup.questions.get(order=1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            MatchupQuestion.objects.create(
                matchup=matchup,
                question_type=first.question_type,
                question_id=first.question_id,
                order=99,
            )

    def test_a_matchup_cannot_have_two_questions_at_the_same_order(self):
        matchup = make_matchup(question_count=3)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MatchupQuestion.objects.create(
                matchup=matchup,
                question_type="single-answer",
                question_id="00000000-0000-0000-0000-000000000000",
                order=1,
            )
