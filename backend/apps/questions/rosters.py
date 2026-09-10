"""Who played for which NBA franchise, read from a baked CSV.

The grid worth asking most often — "name a player who played for both these
teams" — has an answer key that is not a judgement about the sport but a *fact*
about it, and one that runs to tens of thousands of names: every pairing of 72
franchises, every player the two rosters ever shared. Authoring that by hand in
``resources/nba/matrix.yaml`` would be a file nobody can review, wrong the day a
player is traded, and — the part that decides it — the same answer key copied
into every question that uses it.

So a matrix question may declare ``kind: teams`` instead, and its answers come
from here: ``artifacts/nba_player_teams.csv``, one row per player, baked by
``scripts/bake_nba_player_teams.py`` from the league game log. The YAML author
still chooses the *question* — which franchises face which, how long the clock
runs, what level it is — and stops owning the answer key, which is the half that
was never a judgement.

**The CSV is read once per process, lazily.** It is a megabyte, it is only
touched by a question that asked for it, and it never changes while a process
runs — it is a checked-in artifact, replaced by a deploy rather than by a write.
``load_rosters`` is cached on the path for exactly that reason; a test pointing
at a fixture CSV gets its own entry rather than poisoning the real one.

**Players are matched by id, never by name.** Two players have shared a name
before, and a set of *names* per team would score "played for both" for a pair
of namesakes who each played for one of them. Intersecting player *ids* asks the
question that was meant: is there one person in both rosters that this name
names?
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from apps.questions.matching import normalise_answer

__all__ = [
    "TEAM_ROSTERS_CSV",
    "Player",
    "RosterIndex",
    "load_rosters",
]

#: apps/questions/rosters.py -> apps/questions/artifacts/nba_player_teams.csv
TEAM_ROSTERS_CSV = Path(__file__).resolve().parent / "artifacts" / "nba_player_teams.csv"

#: The column separating the franchises in one row's ``teams`` cell.
_TEAM_SEPARATOR = "|"


@dataclass(frozen=True)
class Player:
    """One row of the CSV, as much of it as anything here needs.

    ``probability_score`` is the same 2..10 hand-graded scale
    ``models.MatrixCellAnswer`` carries, baked per player rather than per cell —
    LeBron James is an obvious pick wherever he appears. **Nothing scores with
    it**, for the reason the authored one is not scored with either: credit is
    the fraction of the grid a player filled in, and paying more for a rarer name
    would make two players who both filled the grid correctly score differently.
    It is here because the artifact carries it and deriving it later is the
    expensive order to do it in.
    """

    id: int
    name: str
    probability_score: int


class RosterIndex:
    """Every player, indexed the two ways a team grid asks about them.

    Built once and treated as immutable: ``load_rosters`` hands the same
    instance to every caller in the process.
    """

    def __init__(self, *, players: list[Player], teams_by_player: dict[int, list[str]]):
        self._players = {player.id: player for player in players}

        #: folded title -> the spelling the CSV uses, so a question authored
        #: "los angeles lakers" still reads back as "Los Angeles Lakers" and a
        #: typo is still a load error.
        self._canonical_team: dict[str, str] = {}
        self._by_team: dict[str, set[int]] = {}
        self._by_name: dict[str, set[int]] = {}

        for player in players:
            self._by_name.setdefault(normalise_answer(player.name), set()).add(player.id)
            for title in teams_by_player[player.id]:
                folded = normalise_answer(title)
                self._canonical_team.setdefault(folded, title)
                self._by_team.setdefault(folded, set()).add(player.id)

    # --- What the loader asks -------------------------------------------------

    @property
    def team_titles(self) -> list[str]:
        """Every franchise the artifact knows, alphabetically — the list an
        error message shows an author who mistyped one."""
        return sorted(self._canonical_team.values())

    def canonical_team(self, title: str) -> str | None:
        """The artifact's spelling of ``title``, or ``None`` if it names no
        franchise in it."""
        return self._canonical_team.get(normalise_answer(title))

    def players_for_all(self, titles) -> frozenset[int]:
        """The players who turned out for **every** one of ``titles``.

        Empty for a franchise the artifact does not know, which is deliberate:
        an unknown title is refused at load time (``services.sync``), and a
        question that somehow reached evaluation with one must score its cells
        wrong rather than accept whatever was typed into them.
        """
        folded = [normalise_answer(title) for title in titles]
        if not folded:
            return frozenset()
        found = self._by_team.get(folded[0], set())
        for title in folded[1:]:
            found = found & self._by_team.get(title, set())
            if not found:
                break
        return frozenset(found)

    # --- What the evaluator asks ---------------------------------------------

    def played_for_all(self, *, name: str, titles) -> bool:
        """Did somebody called ``name`` play for every one of ``titles``?

        The name is folded the way every other typed answer is
        (``matching.normalise_answer``) — a player racing a clock types
        ``lebron james``, and a grid that only accepts the capitalisation the
        artifact happens to use is a spelling test.
        """
        named = self._by_name.get(normalise_answer(name))
        if not named:
            return False
        return bool(named & self.players_for_all(titles))

    def player(self, player_id: int) -> Player:
        return self._players[player_id]


def load_rosters(path: Path | None = None) -> RosterIndex:
    """The index, parsed once per process (per path).

    The default is resolved *before* the cache rather than as a default
    argument, so ``load_rosters()`` and ``load_rosters(TEAM_ROSTERS_CSV)`` are
    one cache entry and not two copies of the same megabyte.
    """
    return _load_rosters(path or TEAM_ROSTERS_CSV)


@lru_cache(maxsize=None)
def _load_rosters(path: Path) -> RosterIndex:
    """A missing artifact raises here rather than degrading to an empty index:
    an empty index makes every team grid unanswerable and every cell wrong,
    which would reach two players mid-match as "nothing you type is right"
    instead of reaching a deploy as a missing file.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"The team rosters artifact is missing: {path}. Bake it with "
            f"`uv run python scripts/bake_nba_player_teams.py`."
        )

    players: list[Player] = []
    teams_by_player: dict[int, list[str]] = {}

    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            player_id = int(row["player_id"])
            players.append(
                Player(
                    id=player_id,
                    name=row["player_name"],
                    probability_score=int(row["probability_score"]),
                )
            )
            teams_by_player[player_id] = [
                title.strip()
                for title in row["teams"].split(_TEAM_SEPARATOR)
                if title.strip()
            ]

    return RosterIndex(players=players, teams_by_player=teams_by_player)
