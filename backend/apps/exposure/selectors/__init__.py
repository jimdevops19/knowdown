"""Read side: how exposed a pool of questions already is to a set of players."""

from __future__ import annotations

import random

from apps.exposure.models import QuestionExposure

__all__ = ["exposure_counts", "pick_least_exposed", "repeated_exposures"]


def exposure_counts(*, player_ids, refs) -> dict[tuple, int]:
    """``{(player_id, question_type, question_id): times_seen}`` for every
    row that already exists; a pair absent from this dict has never been
    seen by that player.
    """
    if not refs:
        return {}
    rows = QuestionExposure.objects.filter(
        player_id__in=player_ids,
        question_type__in={ref.question_type for ref in refs},
        question_id__in={ref.question_id for ref in refs},
    ).values_list("player_id", "question_type", "question_id", "times_seen")
    return {
        (player_id, question_type, question_id): times_seen
        for player_id, question_type, question_id, times_seen in rows
    }


def pick_least_exposed(*, player_ids, pool, count, rng=None):
    """``count`` refs out of ``pool``, biased toward whichever have been
    shown the fewest times to the *more*-exposed of ``player_ids``.

    Ranking by ``max()`` across both players rather than either one's own
    count is what stops a repeat from ever reaching someone who hasn't
    earned it just because their opponent has run dry: a question fresh to
    either side always outranks one both have seen. Only once *everyone
    currently in the draw* has exhausted the pool at one exposure count does
    the next tier become fair game, and ties within a tier are broken by a
    reshuffle rather than pool order, so who sees a repeat first is not a
    function of catalog order.

    Signature matches ``apps.questions.selectors.select_questions``'s
    ``choose`` seam — the same way ``rng`` is injectable there, this is how
    ``apps.matches`` supplies a player-aware strategy without
    ``apps.questions`` ever importing this app.
    """
    counts = exposure_counts(player_ids=player_ids, refs=pool)
    ordered = list(pool)
    (rng or random).shuffle(ordered)
    ordered.sort(
        key=lambda ref: max(
            counts.get((player_id, ref.question_type, ref.question_id), 0)
            for player_id in player_ids
        )
    )
    return ordered[:count]


def repeated_exposures(*, min_times_seen: int = 2):
    """Every ``(player, question)`` pair seen at least ``min_times_seen``
    times — the query behind a "players are starting to see repeats" alert.
    """
    return QuestionExposure.objects.filter(
        times_seen__gte=min_times_seen
    ).select_related("player")
