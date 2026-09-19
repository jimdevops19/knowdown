"""Sudden death — the extra question a level match is settled by.

Driven entirely through ``services``, no socket (``backend/CLAUDE.md``'s rule
for the match engine). Every match here is played to a deliberate exact tie,
which is easy to arrange and impossible to arrange by accident: both sides
answer every question wrong, so both finish on nothing.
"""

from __future__ import annotations

from django.test import TestCase

from apps.matches import selectors, services
from apps.matches.constants import MAX_TIEBREAKER_QUESTIONS
from apps.matches.models import Matchup
from apps.matches.services.tiebreak import (
    add_tiebreaker_question,
    is_tied,
    tiebreaker_count,
)
from apps.matches.tests.factories import make_matchup, stock_category
from apps.players.tests.factories import make_player
from apps.questions.selectors import QuestionRef, get_question


def _resolve(matchup_question):
    return get_question(
        ref=QuestionRef(matchup_question.question_type, matchup_question.question_id)
    )


def _option_id(question, *, correct: bool) -> int:
    return question.options.filter(is_correct=correct).first().id


def _answer_question(*, matchup, order: int, correct_for=()) -> None:
    """Both sides answer question ``order``; only players in ``correct_for``
    get it right. Answering closes the question, which is what advances the
    match — the same path a real submission takes."""
    concrete = _resolve(selectors.get_matchup_question(matchup=matchup, order=order))
    for side in selectors.matchup_players(matchup=matchup):
        services.submit_answer(
            matchup=matchup,
            player=side.player,
            order=order,
            payload={
                "type": "single-answer",
                "option_id": _option_id(concrete, correct=side.player in correct_for),
            },
        )


def _play_board(*, matchup, correct_for=()) -> None:
    for order in range(1, matchup.question_count + 1):
        _answer_question(matchup=matchup, order=order, correct_for=correct_for)


class TiedMatchGetsOneMoreQuestionTests(TestCase):
    def test_a_level_match_is_extended_rather_than_completed(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)

        _play_board(matchup=matchup)  # nobody scores: an exact tie

        matchup.refresh_from_db()
        self.assertEqual(matchup.status, Matchup.Status.ACTIVE)
        self.assertEqual(matchup.questions.count(), 4)
        tiebreaker = selectors.get_matchup_question(matchup=matchup, order=4)
        self.assertTrue(tiebreaker.is_tiebreaker)
        self.assertIsNotNone(tiebreaker.started_at)  # dealt, not merely drawn

    def test_the_agreed_match_length_does_not_move(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        _play_board(matchup=matchup)

        matchup.refresh_from_db()
        # The overtime is played *on top of* the three-question match both
        # players agreed to, so `question_count` still says three.
        self.assertEqual(matchup.question_count, 3)

    def test_the_tiebreaker_is_a_question_the_match_has_not_played(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        _play_board(matchup=matchup)

        refs = list(matchup.questions.values_list("question_type", "question_id"))
        self.assertEqual(len(refs), len(set(refs)))

    def test_winning_the_tiebreaker_wins_the_match(self):
        category = stock_category()
        alice = make_player(email="alice-tiebreak@example.com")
        bob = make_player(email="bob-tiebreak@example.com")
        matchup = services.create_matchup(
            category=category, player_one=alice, player_two=bob, question_count=3
        )
        services.start_matchup(matchup=matchup)
        _play_board(matchup=matchup)

        _answer_question(matchup=matchup, order=4, correct_for=(alice,))

        matchup.refresh_from_db()
        self.assertEqual(matchup.status, Matchup.Status.COMPLETED)
        self.assertEqual(matchup.outcome, Matchup.Outcome.PLAYED)
        winner = next(
            side for side in selectors.matchup_players(matchup=matchup) if side.is_winner
        )
        self.assertEqual(winner.player_id, alice.id)

    def test_a_decided_match_is_never_extended(self):
        category = stock_category()
        alice = make_player(email="alice-decided@example.com")
        bob = make_player(email="bob-decided@example.com")
        matchup = services.create_matchup(
            category=category, player_one=alice, player_two=bob, question_count=3
        )
        services.start_matchup(matchup=matchup)
        _play_board(matchup=matchup, correct_for=(alice,))

        matchup.refresh_from_db()
        self.assertEqual(matchup.status, Matchup.Status.COMPLETED)
        self.assertEqual(matchup.questions.count(), 3)
        self.assertEqual(tiebreaker_count(matchup=matchup), 0)


class SuddenDeathEndsSomewhereTests(TestCase):
    def test_a_match_that_stays_level_is_capped_and_settled(self):
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        _play_board(matchup=matchup)

        # Both sides keep answering every tie-breaker wrong: still level.
        for _ in range(MAX_TIEBREAKER_QUESTIONS):
            matchup.refresh_from_db()
            open_question = selectors.current_question(matchup=matchup)
            if open_question is None:
                break
            _answer_question(matchup=matchup, order=open_question.order)

        matchup.refresh_from_db()
        self.assertEqual(matchup.status, Matchup.Status.COMPLETED)
        self.assertEqual(tiebreaker_count(matchup=matchup), MAX_TIEBREAKER_QUESTIONS)

    def test_an_exhausted_category_ends_the_match_rather_than_repeating(self):
        # Exactly three askable questions: the board uses all of them, so
        # there is nothing left to ask when the scores come out level.
        category = stock_category(count=0)
        category = stock_category(category=category, count=3)
        alice = make_player(email="alice-thin@example.com")
        bob = make_player(email="bob-thin@example.com")
        matchup = services.create_matchup(
            category=category, player_one=alice, player_two=bob, question_count=3
        )
        services.start_matchup(matchup=matchup)
        _play_board(matchup=matchup)

        matchup.refresh_from_db()
        self.assertEqual(matchup.status, Matchup.Status.COMPLETED)
        self.assertEqual(matchup.questions.count(), 3)


class TiebreakHelpersTests(TestCase):
    def test_is_tied_reads_the_score_alone(self):
        matchup = make_matchup(question_count=3)
        self.assertTrue(is_tied(matchup=matchup))

        side = matchup.players.first()
        # Total answer time differs, scores do not: still a tie as far as
        # sudden death is concerned — the time rule is what it runs before.
        side.total_answer_time_ms = 5_000
        side.save(update_fields=["total_answer_time_ms"])
        self.assertTrue(is_tied(matchup=matchup))

        side.score = 10
        side.save(update_fields=["score"])
        self.assertFalse(is_tied(matchup=matchup))

    def test_asking_for_a_tiebreaker_on_a_decided_match_is_not_an_error(self):
        matchup = make_matchup(question_count=3)
        side = matchup.players.first()
        side.score = 10
        side.save(update_fields=["score"])

        self.assertIsNone(add_tiebreaker_question(matchup=matchup))
        self.assertEqual(matchup.questions.count(), 3)
