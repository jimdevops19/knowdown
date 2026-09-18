"""Career totals per player, read from a baked CSV — the answer key for
"name as many as you can".

The sibling of :mod:`apps.questions.rosters`, and for the same reason. A
question like *"name as many players as you can with 1,000 career
three-pointers"* has an answer key that is a **fact** rather than a judgement:
it is every player above a line in a column of numbers, which runs to hundreds
of names, changes every night the league plays, and would be the same list
copied into the next question that asked about 1,200. So the file authors the
*question* — the stat, the line, how many points are worth full credit — and
stops owning the answer key.

``artifacts/nba_player_career_stats.csv`` is that column and every other one
baked so far, one row per player::

    player_id,player_name,fg3m
    201939,Stephen Curry,4058

**One file, many columns, one script per column.** Adding "free throws missed"
is a new script under ``scripts/career_stats/`` that writes a new column into
the same file; nothing here changes, because this module reads whatever stat
columns the artifact happens to carry and a question naming one that is not
there is refused when the YAML is loaded (``schemas.NameAsManySpec``) rather
than mid-match.

**The popularity score is joined, not repeated.** How obvious a pick a player
is — ``probability_score``, 2..10 — is already baked into
``nba_player_teams.csv`` and is the same judgement wherever it is read, so this
artifact does not carry a second copy of it that could disagree. The two files
are joined on ``player_id``, never on name, for the reason
:mod:`apps.questions.rosters` intersects ids: two players have shared a name.

**Here, unlike everywhere else, the score is what you are paid.** Every other
type treats ``probability_score`` as a clue to be hidden and never as credit —
two players who both filled a grid correctly must score the same. This type is
the exception that proves it: the question is not *whether* you can name one,
it is *how deep you can go*, so naming Vince Carter has to be worth more than
naming Stephen Curry or the whole mode is "type the five most famous shooters".
The scale is the same 2..10, so a deep cut is worth five obvious names.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from apps.questions.matching import normalise_answer
from apps.questions.models import DEFAULT_PROBABILITY_SCORE, StatComparison
from apps.questions.rosters import TEAM_ROSTERS_CSV, load_rosters

__all__ = [
    "CAREER_STATS_CSV",
    "CareerStatsIndex",
    "Qualifiers",
    "StatPlayer",
    "comparison_holds",
    "load_career_stats",
]

#: apps/questions/career_stats.py -> apps/questions/artifacts/nba_player_career_stats.csv
CAREER_STATS_CSV = (
    Path(__file__).resolve().parent / "artifacts" / "nba_player_career_stats.csv"
)

#: The columns naming *who* a row is about. Everything else in the header is a
#: stat a question may be authored against — which is what makes expanding the
#: artifact a job with no code in it.
IDENTITY_COLUMNS = ("player_id", "player_name")


def comparison_holds(*, comparison: str, value: float, threshold: float) -> bool:
    """Does ``value`` fall on the qualifying side of the line?

    The comparison is ``models.StatComparison``'s string, which is the one
    vocabulary the YAML, the row and this module all speak. Anything that is not
    ``at-most`` reads as ``at-least`` — the default and by far the common case —
    rather than raising: a row carrying a comparison this build has never heard
    of is a downgrade, and the question it belongs to should be askable rather
    than unscoreable.
    """
    if comparison == StatComparison.AT_MOST:
        return value <= threshold
    return value >= threshold


@dataclass(frozen=True)
class StatPlayer:
    """One player who clears the line, and what naming him is worth.

    ``probability_score`` comes from the roster artifact (see the module
    docstring) and falls back to ``DEFAULT_PROBABILITY_SCORE`` for a player the
    two files do not share — a middle grade, meaning *ungraded*, which is the
    same thing an ungraded matrix answer gets. A player missing from the roster
    bake is a player the game log recorded stats for and no team for, which
    should not happen and must not be worth zero if it does: an answer that is
    right has to be worth something.
    """

    id: int
    name: str
    value: float
    probability_score: int


@dataclass(frozen=True)
class Qualifiers:
    """Everybody who clears one line of one stat, indexed for scoring.

    Built once per (stat, comparison, threshold) and cached on the index: a
    question asks the same one of these on every submission, and rescanning
    every player per name typed would be the obvious way to make a 30-second
    question the slowest thing in the match.

    ``players`` is ordered **most obvious first** (lowest
    ``probability_score``), which is the order the answer key reveals in and
    the order a person would have thought of them in.
    """

    stat: str
    players: tuple[StatPlayer, ...]
    _by_name: dict[str, StatPlayer]

    @property
    def total_score(self) -> int:
        """Every point on the board — what naming *everybody* would be worth.

        The ceiling a question's ``target_score`` is checked against when the
        file is loaded: a target above this is a question nobody can complete,
        which is a typo rather than a hard question.
        """
        return sum(player.probability_score for player in self.players)

    def find(self, name: str) -> StatPlayer | None:
        """The qualifying player of this name, or ``None``.

        Folded the way every typed answer in this app is
        (``matching.normalise_answer``) — somebody racing a clock types
        ``ray allen``.

        Namesakes are resolved to the one with the **better figure**, which is
        the only reading that does not punish a player for a coincidence: if two
        Chris Johnsons played and one of them cleared the line, the person who
        typed the name was naming that one.
        """
        return self._by_name.get(normalise_answer(name))


class CareerStatsIndex:
    """The artifact, and the questions a ``name-as-many`` question asks of it.

    Built once and treated as immutable — ``load_career_stats`` hands the same
    instance to every caller in the process — apart from the qualifier cache,
    which is memoisation of a pure function of the rows.
    """

    def __init__(
        self,
        *,
        stats: tuple[str, ...],
        players: dict[int, tuple[str, int]],
        values: dict[str, dict[int, float]],
    ):
        self._stats = stats
        #: ``{player_id: (name, probability_score)}``, kept apart from
        #: ``{stat: {player_id: value}}`` because the second is what a question
        #: scans and the first is only needed for the handful of ids that clear
        #: the line.
        self._players = players
        self._values = values
        self._qualifier_cache: dict[tuple[str, str, float], Qualifiers] = {}

    # --- What the loader asks -------------------------------------------------

    @property
    def stats(self) -> tuple[str, ...]:
        """Every stat column the artifact carries, in file order — the list an
        error message shows an author who mistyped one."""
        return self._stats

    def has_stat(self, stat: str) -> bool:
        return stat in self._stats

    # --- What the evaluator and the answer key ask ---------------------------

    def qualifiers(self, *, stat: str, comparison: str, threshold: float) -> Qualifiers:
        """Everybody who clears this line, cached per question shape.

        An unknown stat yields an empty set rather than raising, deliberately,
        and it is the same decision ``rosters.players_for_all`` makes about an
        unknown franchise: the load-time check is what refuses a mistyped stat
        (``schemas.NameAsManySpec``), and a question that somehow reached
        evaluation with one must score every name wrong rather than accept
        whatever was typed.
        """
        key = (stat, comparison, float(threshold))
        cached = self._qualifier_cache.get(key)
        if cached is not None:
            return cached

        players = [
            StatPlayer(
                id=player_id,
                name=self._players[player_id][0],
                value=value,
                probability_score=self._players[player_id][1],
            )
            for player_id, value in self._values.get(stat, {}).items()
            if player_id in self._players
            and comparison_holds(comparison=comparison, value=value, threshold=threshold)
        ]
        players.sort(key=lambda player: (player.probability_score, -player.value, player.name))

        by_name: dict[str, StatPlayer] = {}
        for player in players:
            folded = normalise_answer(player.name)
            incumbent = by_name.get(folded)
            if incumbent is None or player.value > incumbent.value:
                by_name[folded] = player

        qualifiers = Qualifiers(stat=stat, players=tuple(players), _by_name=by_name)
        self._qualifier_cache[key] = qualifiers
        return qualifiers


def load_career_stats(
    path: Path | None = None, *, rosters_path: Path | None = None
) -> CareerStatsIndex:
    """The index, parsed once per process (per pair of paths).

    Both defaults are resolved *before* the cache rather than as default
    arguments, so ``load_career_stats()`` and the explicit spelling are one
    cache entry rather than two copies of the same megabyte — the same
    arrangement ``rosters.load_rosters`` makes, for the same reason.
    """
    return _load_career_stats(path or CAREER_STATS_CSV, rosters_path or TEAM_ROSTERS_CSV)


@lru_cache(maxsize=None)
def _load_career_stats(path: Path, rosters_path: Path) -> CareerStatsIndex:
    """A missing artifact raises here rather than degrading to an empty index,
    for the reason a missing roster artifact does: an empty index makes every
    name wrong, which reaches two players mid-match as "nothing you type counts"
    instead of reaching a deploy as a missing file."""
    if not path.exists():
        raise FileNotFoundError(
            f"The career stats artifact is missing: {path}. Bake it with "
            f"`uv run python scripts/career_stats/bake_three_pointers_made.py`."
        )

    rosters = load_rosters(rosters_path)

    players: dict[int, tuple[str, int]] = {}
    values: dict[str, dict[int, float]] = {}
    stats: tuple[str, ...] = ()

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        stats = tuple(
            column for column in (reader.fieldnames or ()) if column not in IDENTITY_COLUMNS
        )
        for stat in stats:
            values[stat] = {}

        for row in reader:
            player_id = int(row["player_id"])
            players[player_id] = (
                row["player_name"],
                _probability_score(rosters, player_id),
            )
            for stat in stats:
                raw = (row.get(stat) or "").strip()
                if not raw:
                    # An empty cell is "this stat was never measured for him"
                    # — a player who retired before the three-point line, or a
                    # column baked over a narrower range of seasons. Absent,
                    # not zero: a question asking for *at most* 10 threes must
                    # not be answered by every player of the 1950s.
                    continue
                values[stat][player_id] = float(raw)

    return CareerStatsIndex(stats=stats, players=players, values=values)


def _probability_score(rosters, player_id: int) -> int:
    """The player's fame grade from the roster artifact, or the middle of the
    scale for one the two bakes do not share."""
    try:
        return rosters.player(player_id).probability_score
    except KeyError:
        return DEFAULT_PROBABILITY_SCORE
