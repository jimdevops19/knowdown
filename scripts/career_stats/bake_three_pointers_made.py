"""Bake the ``fg3m`` column of ``nba_player_career_stats.csv``: career
three-pointers made, every player in NBA history.

    uv run python scripts/career_stats/bake_three_pointers_made.py
    uv run python scripts/career_stats/bake_three_pointers_made.py --offline

The first stat column of the shared career-stats artifact, and the template for
every one after it: this file is a docstring, a :class:`StatSpec` and a call to
``_common.bake``. See ``_common.py`` for what the artifact is, why there is one
of it, and why the popularity score is *not* in it.

FEEDS
    ``type: name-as-many`` questions authored against ``stat: fg3m`` — "name as
    many players as you can with 1,000 career threes", which is scored by the
    popularity of the names a player reaches for
    (``apps.questions.career_stats``).

WHY 1979-80
    The three-point line arrived in 1979-80. Every season before it is a column
    of zeros for a shot nobody was allowed to take, and confirming that costs
    thirty-three requests against an endpoint that throttles hard. The players
    of those eras still appear in the artifact the moment another stat script
    measures them — their ``fg3m`` cell is left *empty* rather than zeroed,
    which is the honest distinction: Bob Cousy did not miss his threes, he was
    never offered any. (``_common.merge_column`` is where that rule lives.)

    A player whose career straddles 1979-80 is counted correctly regardless: the
    seasons before it contributed nothing to a total that starts at zero.
"""

from __future__ import annotations

import sys

from _common import StatSpec, bake

#: The three-point line's first season, as a start year (1979-80).
FIRST_THREE_POINT_SEASON = 1979

SPEC = StatSpec(
    column="fg3m",
    gamelog_field="FG3M",
    first_season=FIRST_THREE_POINT_SEASON,
)


if __name__ == "__main__":
    raise SystemExit(bake(SPEC, sys.argv[1:]))
