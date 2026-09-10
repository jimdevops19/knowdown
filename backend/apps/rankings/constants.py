"""The rating arithmetic's one tuning knob.

The ladder is Elo-style, and deliberately simpler than a tournament ladder's:
there is no guest handling, no race-length scaling, no competitive-vs-friendly
split to decide before a result counts — every completed matchup, played or
abandoned (``apps.matches.Matchup.Outcome``), moves both players' rating in its
category exactly once. See ``apps.rankings.services.ratings`` for the update
itself.

``DEFAULT_PLAYER_RATING`` is *not* redefined here — it lives in
``apps.matches.constants`` because seeding happens the moment a matchup needs a
rating that is not there yet, not on a schedule ``rankings`` owns (see that
module's docstring). This module imports it rather than duplicating the number.
"""

from __future__ import annotations

__all__ = ["K_FACTOR"]

#: How many points a single result moves a rating. Applied symmetrically: the
#: winner gains ``K_FACTOR * (1 - expected)``, the loser loses the same amount
#: — Elo's usual property that a match's points are conserved between the two
#: players. Chess-sized (the canonical value for a developing player) rather
#: than tournament-sized, because a best-of-X trivia matchup is a much shorter
#: signal than a chess game and should not swing a ladder on one result.
K_FACTOR = 32
