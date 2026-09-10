"""Achievement test fixtures: playing a match to a given result, and manufacturing
a player's answer history cheaply for the one rule (Hundred Questions Answered)
that needs more of it than a handful of real matches is worth building."""

from __future__ import annotations

import uuid

from apps.categories.models import Category
from apps.matches import services as match_services
from apps.matches.models import Matchup, MatchupQuestion, PlayerAnswer
from apps.matches.tests.factories import stock_category
from apps.players.models import Player
from apps.questions.selectors import QuestionRef, get_question


def play_matchup(
    *,
    alice: Player,
    bob: Player,
    category: Category | None = None,
    question_count: int = 3,
    alice_correct: bool = True,
    bob_correct: bool = False,
) -> Matchup:
    """A real matchup, played through ``apps.matches.services`` to
    ``COMPLETED`` — the path that actually fires
    ``award_achievements_for_matchup``. Alice and Bob answer every question the
    same way throughout, which is enough to control who wins."""
    category = stock_category(category=category)
    matchup = match_services.create_matchup(
        category=category, player_one=alice, player_two=bob, question_count=question_count
    )
    match_services.start_matchup(matchup=matchup)

    for order in range(1, question_count + 1):
        matchup.refresh_from_db()
        row = matchup.questions.get(order=order)
        concrete = get_question(ref=QuestionRef(row.question_type, row.question_id))
        correct_id = concrete.options.get(is_correct=True).id
        wrong_id = concrete.options.filter(is_correct=False).first().id
        match_services.submit_answer(
            matchup=matchup, player=alice, order=order,
            payload={
                "type": "single-answer",
                "option_id": correct_id if alice_correct else wrong_id,
            },
        )
        match_services.submit_answer(
            matchup=matchup, player=bob, order=order,
            payload={
                "type": "single-answer",
                "option_id": correct_id if bob_correct else wrong_id,
            },
        )
    matchup.refresh_from_db()
    return matchup


def give_answer_history(*, player: Player, count: int) -> None:
    """``count`` extra ``PlayerAnswer`` rows for ``player``, on a disposable
    matchup nobody plays through the services. Only the *count* matters to
    "Hundred Questions Answered" — building that many real matches would be
    correct but pointlessly slow."""
    category = stock_category(count=1)
    matchup = Matchup.objects.create(category=category, question_count=count)
    stamp = uuid.uuid4().hex[:8]
    questions = MatchupQuestion.objects.bulk_create(
        MatchupQuestion(
            matchup=matchup,
            question_type="single-answer",
            question_id=f"{stamp}-{index}",
            order=index,
        )
        for index in range(1, count + 1)
    )
    PlayerAnswer.objects.bulk_create(
        PlayerAnswer(
            matchup_question=question,
            player=player,
            answer={},
            is_correct=True,
            score=1.0,
            points=100,
            response_time_ms=1000,
        )
        for question in questions
    )
