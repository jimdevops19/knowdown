"""The whole game, callable from a test.

Every rule of a match lives here, keyword-only and ``@transaction.atomic``,
with no knowledge of WebSockets — Phase D adds a transport over the top
(``backend/CLAUDE.md``). A consumer, when it exists, will do nothing but
receive → validate → call one of these → broadcast.

Two rules run through all of it:

**Evaluation is not this app's to know.** ``submit_answer`` asks
``apps.questions.services.evaluate_answer`` what a submission is worth and
never inspects a question's own answer field — the dependency the ``(type,
id)`` pair in ``MatchupQuestion`` exists to keep one-directional.

**The server is the only clock.** ``start_question`` stamps ``started_at``;
``submit_answer`` measures the gap between that timestamp and its own call to
``timezone.now()``. There is no parameter here a client could use to report
its own elapsed time — accepting one would make every match winnable with a
patched client.

``complete_matchup`` and ``abandon_matchup`` — the two ways a matchup becomes
``COMPLETED`` — both call, in order, ``apps.achievements.services
.award_achievements_for_matchup`` and then ``apps.rankings.services
.update_ratings_for_matchup``, once they have decided the winner. The order is
deliberate: achievements are checked while each side's ``Ranking`` still holds
the rating they took into this result, which is what "Beat a Higher Rated
Player" reads. Either way, a match, played out or left mid-way, always checks
badges and moves ratings exactly once.
"""

from __future__ import annotations

import random

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.achievements.services import award_achievements_for_matchup
from apps.categories.models import Category
from apps.core_common.exceptions import Conflict, NotFound, ValidationFailed
from apps.matches import selectors
from apps.matches.constants import (
    MATCH_QUESTION_COUNTS,
    PLAYERS_PER_MATCHUP,
    score_answer,
    time_limit_ms_for,
)
from apps.matches.models import Matchup, MatchupPlayer, MatchupQuestion, PlayerAnswer
from apps.players.models import Player
from apps.questions.selectors import QuestionRef
from apps.questions.selectors import get_question as get_concrete_question
from apps.questions.selectors import select_questions
from apps.questions.services.evaluation import evaluate_answer
from apps.rankings.services import update_ratings_for_matchup

__all__ = [
    "abandon_matchup",
    "complete_matchup",
    "complete_question",
    "create_matchup",
    "return_player_to_matchmaking",
    "select_match_questions",
    "start_matchup",
    "start_question",
    "submit_answer",
]


@transaction.atomic
def create_matchup(
    *,
    category: Category,
    player_one: Player,
    player_two: Player,
    question_count: int | None = None,
    rng: random.Random | None = None,
) -> Matchup:
    """A new, unstarted matchup with its questions already drawn.

    The question count is chosen **once**, here, for both players — never per
    question — and so is the question list (``select_match_questions``): a
    matchup is a race through one fixed board, not two independent quizzes.
    """
    if player_one.pk == player_two.pk:
        raise ValidationFailed("A player cannot be matched against themselves.")

    if question_count is None:
        question_count = (rng or random).choice(MATCH_QUESTION_COUNTS)
    elif question_count not in MATCH_QUESTION_COUNTS:
        raise ValidationFailed(
            f"question_count must be one of {MATCH_QUESTION_COUNTS}, got {question_count}."
        )

    matchup = Matchup.objects.create(category=category, question_count=question_count)
    MatchupPlayer.objects.bulk_create(
        [
            MatchupPlayer(matchup=matchup, player=player_one),
            MatchupPlayer(matchup=matchup, player=player_two),
        ]
    )
    select_match_questions(matchup=matchup, rng=rng)
    return matchup


@transaction.atomic
def select_match_questions(
    *, matchup: Matchup, rng: random.Random | None = None
) -> list[MatchupQuestion]:
    """Draw ``matchup.question_count`` questions and freeze them onto the
    matchup, in order. Refuses to redraw a matchup that already has a board —
    the board is fixed the moment it exists, so both players see one game."""
    if matchup.questions.exists():
        raise Conflict("Questions have already been selected for this matchup.")

    refs = select_questions(
        category=matchup.category, count=matchup.question_count, rng=rng
    )
    rows = MatchupQuestion.objects.bulk_create(
        [
            MatchupQuestion(
                matchup=matchup,
                question_type=ref.question_type,
                question_id=ref.question_id,
                order=order,
            )
            for order, ref in enumerate(refs, start=1)
        ]
    )
    return rows


@transaction.atomic
def start_matchup(*, matchup: Matchup) -> Matchup:
    """Marks the matchup live and starts its first question."""
    if matchup.status != Matchup.Status.WAITING:
        raise Conflict(f"Matchup {matchup.pk} is {matchup.status}, not waiting.")
    if matchup.players.count() != PLAYERS_PER_MATCHUP:
        raise ValidationFailed(
            f"A matchup needs exactly {PLAYERS_PER_MATCHUP} players to start."
        )
    if not matchup.questions.exists():
        raise ValidationFailed("Cannot start a matchup with no questions selected.")

    matchup.status = Matchup.Status.ACTIVE
    matchup.started_at = timezone.now()
    matchup.save(update_fields=["status", "started_at"])
    start_question(matchup=matchup, order=1)
    return matchup


@transaction.atomic
def start_question(*, matchup: Matchup, order: int) -> MatchupQuestion:
    """Stamps ``T0`` for one question. Idempotent: called again for a
    question already open, it just returns it — a reconnecting player asking
    for the current question (Phase D) is not an error."""
    if matchup.status != Matchup.Status.ACTIVE:
        raise Conflict(f"Matchup {matchup.pk} is {matchup.status}, not active.")

    question = selectors.get_matchup_question(matchup=matchup, order=order)
    if question.started_at is None:
        question.started_at = timezone.now()
        question.save(update_fields=["started_at"])
    return question


@transaction.atomic
def submit_answer(
    *, matchup: Matchup, player: Player, order: int, payload: dict
) -> PlayerAnswer:
    """Score one player's submission to one question.

    ``payload`` is the answer shape alone (``{"option_id": ...}``) — there is
    no time field to read, lying or otherwise; the schemas
    ``evaluate_answer`` validates against are ``extra="forbid"``, so a client
    that tacks one on gets ``ValidationFailed`` rather than a stopwatch it
    controls.

    Idempotent per ``(matchup_question, player)``: a retried submission
    returns the row already scored rather than scoring it twice, whether the
    first attempt is found by a plain lookup or by racing an insert into the
    unique constraint that backs it.
    """
    question = selectors.get_matchup_question(matchup=matchup, order=order)
    if question.started_at is None:
        raise Conflict(f"Question {order} of matchup {matchup.pk} has not started yet.")

    existing = PlayerAnswer.objects.filter(matchup_question=question, player=player).first()
    if existing is not None:
        return existing

    if question.completed_at is not None:
        raise Conflict(
            f"Question {order} of matchup {matchup.pk} is already closed.",
            code="question_already_completed",
        )

    time_limit_ms = time_limit_ms_for(question.question_type)
    now = timezone.now()
    elapsed_ms = int((now - question.started_at).total_seconds() * 1000)
    if elapsed_ms > time_limit_ms:
        raise Conflict(
            f"Question {order} of matchup {matchup.pk} timed out before this answer arrived.",
            code="question_time_expired",
        )
    response_time_ms = max(0, min(elapsed_ms, time_limit_ms))

    concrete_question = get_concrete_question(
        ref=QuestionRef(question.question_type, question.question_id)
    )
    result = evaluate_answer(question=concrete_question, submitted=payload)
    points = score_answer(credit=result.score, response_time_ms=response_time_ms, time_limit_ms=time_limit_ms)

    try:
        with transaction.atomic():
            answer = PlayerAnswer.objects.create(
                matchup_question=question,
                player=player,
                answer=dict(payload),
                is_correct=result.is_correct,
                score=result.score,
                points=points,
                response_time_ms=response_time_ms,
            )
    except IntegrityError:
        # Lost the race to a concurrent retry of the same submission — the
        # constraint this is backstopping already has the real row.
        return PlayerAnswer.objects.get(matchup_question=question, player=player)

    match_player = (
        MatchupPlayer.objects.select_for_update()
        .get(matchup=matchup, player=player)
    )
    match_player.score += points
    match_player.total_answer_time_ms += response_time_ms
    if result.is_correct:
        match_player.correct_answers += 1
    match_player.save(update_fields=["score", "total_answer_time_ms", "correct_answers"])

    if question.answers.count() >= matchup.players.count():
        complete_question(matchup=matchup, order=order)

    return answer


@transaction.atomic
def complete_question(*, matchup: Matchup, order: int) -> MatchupQuestion:
    """Closes one question and advances the match.

    Refuses to close early: a question with players still owed an answer may
    only be completed once its time limit has actually elapsed — otherwise a
    client could race the opponent's clock by asking the server to call the
    question over. A player who never answers in time simply has no
    ``PlayerAnswer`` row; there is nothing else to score.
    """
    question = selectors.get_matchup_question(matchup=matchup, order=order)
    if question.completed_at is not None:
        return question  # already closed — idempotent, like everything else here

    answered = question.answers.count()
    total_players = matchup.players.count()
    deadline_passed = (
        question.started_at is not None
        and (timezone.now() - question.started_at).total_seconds() * 1000
        >= time_limit_ms_for(question.question_type)
    )
    if answered < total_players and not deadline_passed:
        raise Conflict(
            f"Question {order} of matchup {matchup.pk} still has players who "
            f"may answer before the time limit.",
            code="question_still_open",
        )

    question.completed_at = timezone.now()
    question.save(update_fields=["completed_at"])

    if order < matchup.question_count:
        start_question(matchup=matchup, order=order + 1)
    else:
        complete_matchup(matchup=matchup)
    return question


@transaction.atomic
def complete_matchup(*, matchup: Matchup) -> Matchup:
    """Ends the matchup on its last question and decides the winner.

    Higher total score wins; a tie on score falls to whoever spent less total
    time; a tie on both leaves neither side marked a winner rather than
    picking one arbitrarily. Idempotent — a matchup already ``COMPLETED`` is
    returned unchanged, since ``complete_question`` may call this and
    ``abandon_matchup`` may race it.
    """
    if matchup.status == Matchup.Status.COMPLETED:
        return matchup

    players = list(selectors.matchup_players(matchup=matchup))
    if len(players) == PLAYERS_PER_MATCHUP:
        first, second = players
        if first.score != second.score:
            winner = first if first.score > second.score else second
        elif first.total_answer_time_ms != second.total_answer_time_ms:
            winner = (
                first if first.total_answer_time_ms < second.total_answer_time_ms else second
            )
        else:
            winner = None
        for side in players:
            side.is_winner = side is winner
        MatchupPlayer.objects.bulk_update(players, ["is_winner"])

    matchup.status = Matchup.Status.COMPLETED
    matchup.outcome = Matchup.Outcome.PLAYED
    matchup.completed_at = timezone.now()
    matchup.save(update_fields=["status", "outcome", "completed_at"])
    award_achievements_for_matchup(matchup=matchup)
    update_ratings_for_matchup(matchup=matchup)
    return matchup


@transaction.atomic
def abandon_matchup(*, matchup: Matchup, leaving_player: Player) -> Matchup:
    """A player leaves mid-match: the opponent is awarded the win, the
    matchup reaches a terminal state, and no further question is started.

    Settled here rather than left open: voiding the result would erase
    whatever the remaining player had already earned, and refusing to end the
    matchup would strand it active forever with nobody left to answer.
    Awarding the win is also what lets ``apps.rankings`` (step 17) treat this
    exactly like any other ``complete_matchup`` — an abandoned matchup still
    updates both sides' ratings once.
    """
    leaving_side = selectors.get_matchup_player(matchup=matchup, player=leaving_player)
    if leaving_side.left_at is not None:
        return matchup  # already recorded — idempotent against a repeated disconnect

    if matchup.status not in (Matchup.Status.WAITING, Matchup.Status.ACTIVE):
        raise Conflict(f"Matchup {matchup.pk} is {matchup.status}, and cannot be abandoned.")

    now = timezone.now()
    leaving_side.left_at = now
    leaving_side.is_winner = False
    leaving_side.save(update_fields=["left_at", "is_winner"])

    try:
        remaining_side = selectors.opponent_of(matchup=matchup, player=leaving_player)
    except NotFound:
        remaining_side = None
    if remaining_side is not None:
        remaining_side.is_winner = True
        remaining_side.save(update_fields=["is_winner"])

    open_question = selectors.current_question(matchup=matchup)
    if open_question is not None:
        # Leaves nothing "in progress": the question stops rather than
        # waiting out a clock nobody is left to answer against.
        open_question.completed_at = now
        open_question.save(update_fields=["completed_at"])

    matchup.status = Matchup.Status.COMPLETED
    matchup.outcome = Matchup.Outcome.ABANDONED
    matchup.completed_at = now
    matchup.save(update_fields=["status", "outcome", "completed_at"])
    award_achievements_for_matchup(matchup=matchup)
    update_ratings_for_matchup(matchup=matchup)
    return matchup


def return_player_to_matchmaking(*, matchup: Matchup, player: Player) -> Player:
    """The seam Phase D's matchmaking pool (step 14) will call once it exists.

    Today there is no pool — one logical Redis queue, not a database row per
    waiting player, is a Phase D concern — so this is deliberately a
    validation stub: it confirms the matchup is actually over for this player
    before handing them back, and is the one place that check will live when
    there is somewhere to hand them back *to*.
    """
    if matchup.status != Matchup.Status.COMPLETED:
        raise ValidationFailed(
            f"Matchup {matchup.pk} is {matchup.status}; a player may only return "
            f"to matchmaking once it has finished."
        )
    selectors.get_matchup_player(matchup=matchup, player=player)  # 404s if not a participant
    return player
