"""Sudden death: what happens when the last question closes and the scores
are level.

``complete_matchup`` has always been able to settle a tie — lower total answer
time wins, and a tie on that too leaves nobody marked the winner. Both of
those decide a race by something other than the race, which is the right
*last* answer and a poor first one. So before either applies, the engine asks
this module for one more question: an extra ``MatchupQuestion`` appended past
``Matchup.question_count``, drawn the same way the board itself was drawn (at
random, biased away from what either player has already been shown) and played
through exactly the same ``start_question``/``submit_answer``/
``complete_question`` path as any other question. Nothing in the transport,
the bots or the client needs a special case for it: the tie-breaker simply
*is* the next question, and ``complete_question`` asks again when it closes.

``Matchup.question_count`` deliberately does **not** move. It is the length
both players agreed to at ``create_matchup`` ("a five-question match"), and the
questions past it are the overtime — which is why the extra rows carry
``MatchupQuestion.is_tiebreaker`` instead, and why a board is still "frozen"
in the sense ``select_match_questions`` means it.

Two things bound the overtime, and either one hands the match back to
``complete_matchup``'s original tie rules:

* :data:`~apps.matches.constants.MAX_TIEBREAKER_QUESTIONS`, so two evenly
  matched players cannot keep a match open forever; and
* the catalog — a category with nothing left that this matchup has not already
  played has no question to ask, and a repeat would be a tie-breaker one side
  may have seen minutes ago.
"""

from __future__ import annotations

import random

from django.db import transaction

from apps.exposure.selectors import pick_least_exposed
from apps.exposure.services import record_exposures
from apps.matches import selectors
from apps.matches.constants import MAX_TIEBREAKER_QUESTIONS, PLAYERS_PER_MATCHUP
from apps.matches.models import Matchup, MatchupQuestion
from apps.questions.selectors import QuestionRef, question_pool
from shared.logging import get_logger, labels

logger = get_logger(__name__)

__all__ = [
    "add_tiebreaker_question",
    "is_tied",
    "tiebreaker_count",
]


def is_tied(*, matchup: Matchup) -> bool:
    """Whether the two sides are on **exactly** the same score.

    Only the score — not the total answer time the old rule falls back to.
    That fallback is what a tie-breaker exists to be asked before, so reading
    it here would mean never asking one.
    """
    scores = [side.score for side in selectors.matchup_players(matchup=matchup)]
    return len(scores) == PLAYERS_PER_MATCHUP and scores[0] == scores[1]


def tiebreaker_count(*, matchup: Matchup) -> int:
    """How many sudden-death questions this matchup has already been given."""
    return matchup.questions.filter(is_tiebreaker=True).count()


@transaction.atomic
def add_tiebreaker_question(
    *, matchup: Matchup, rng: random.Random | None = None
) -> MatchupQuestion | None:
    """One more question for a level match, or ``None`` if there is not one to
    give.

    ``None`` — the cap is reached, the catalog is exhausted, or the scores are
    not actually level — is a normal answer, not a failure: the caller
    (``services.complete_question``) simply finishes the match on the rules it
    had before. Nothing here raises for a matchup that does not need a
    tie-breaker, so the caller can ask unconditionally.

    The draw excludes every question already on this board, so sudden death is
    never a question one side answered ten seconds ago; and it goes through
    ``pick_least_exposed``/``record_exposures`` like the original board, so a
    question spent here is a question neither player is shown again soon.
    """
    if not is_tied(matchup=matchup):
        return None
    if tiebreaker_count(matchup=matchup) >= MAX_TIEBREAKER_QUESTIONS:
        return None

    played = set(matchup.questions.values_list("question_type", "question_id"))
    pool = [
        ref
        for ref in question_pool(category=matchup.category)
        if ref.as_tuple() not in played
    ]
    if not pool:
        # Nothing left to ask that this matchup has not already asked. The
        # match still ends — on total answer time, or as a draw — rather than
        # replaying a question either player has just seen.
        logger.warning(
            "No tie-breaker available — category exhausted for this matchup",
            category=labels.category(matchup.category),
            action="tiebreak",
        )
        return None

    player_ids = [side.player_id for side in matchup.players.all()]
    ref: QuestionRef = pick_least_exposed(
        player_ids=player_ids, pool=pool, count=1, rng=rng
    )[0]
    last_order = max(question.order for question in matchup.questions.all())
    question = MatchupQuestion.objects.create(
        matchup=matchup,
        question_type=ref.question_type,
        question_id=ref.question_id,
        order=last_order + 1,
        is_tiebreaker=True,
    )
    record_exposures(player_ids=player_ids, refs=[ref])
    logger.info(
        "Scores level — playing a tie-breaker question",
        category=labels.category(matchup.category),
        question_type=ref.question_type,
        action="tiebreak",
    )
    return question
