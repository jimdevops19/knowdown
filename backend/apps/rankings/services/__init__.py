"""The write side of the ladder — Elo, one category at a time.

Everything lives in ``ratings``; this module just re-exports the names a
caller needs, the way ``apps.questions.services`` fronts ``evaluation`` and
``sync``.
"""

from __future__ import annotations

from apps.rankings.services.ratings import (
    ensure_ranking,
    expected_score,
    seed_all_players,
    update_rating,
    update_ratings_for_matchup,
)

__all__ = [
    "ensure_ranking",
    "expected_score",
    "seed_all_players",
    "update_rating",
    "update_ratings_for_matchup",
]
