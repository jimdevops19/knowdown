"""One CSV of career totals, and the machinery every stat script shares.

    backend/apps/questions/artifacts/nba_player_career_stats.csv

        player_id,player_name,fg3m
        2544,LeBron James,2600
        201939,Stephen Curry,4058
        ...

WHY ONE FILE AND NOT ONE PER STAT
    The questions this feeds — "name as many players as you can with 1,000
    career threes", and tomorrow "…who missed 2,000 free throws" — are all the
    same question over a different column. A file per stat would mean a player's
    identity (his id, the way his name is spelled) copied into every one of
    them, and eight files to re-key the day the league renames somebody. So
    there is **one** artifact, and a stat script's whole job is to add or
    refresh **one column** of it: everything else in the file is read and
    written back untouched.

    That is what makes expanding it cheap. A new stat is a new script in this
    folder — thirty lines, mostly a docstring — which declares the column it
    owns and the box-score field it sums, and the question catalog picks the
    column up with no backend change at all: ``apps.questions.career_stats``
    reads whatever columns the file happens to have, and a YAML question naming
    a column that is not there is refused at load time.

WHERE THE NUMBERS COME FROM
    The league-wide player game log, exactly as ``scripts/bake_nba_player_teams
    .py`` pulls it — one request per *season* rather than one per player, and
    every response cached to a tmp file before anything is derived from it. The
    two bakes therefore **share a cache**: if the teams artifact has been baked
    on this machine, every stat script here runs offline and in seconds, and
    vice versa. That is why the fetching code is imported from there rather than
    copied: two rate limiters pointed at the same endpoint would be two ways to
    get blocked.

    Summing a box-score column over every game a player played is a *career
    total* by construction, and it is the only way to get one that reaches back
    past 1996-97 — which ``leaguedashplayerstats`` does not.

POPULARITY IS NOT IN THIS FILE
    A player's ``probability_score`` — how obvious a pick he is, 2..10 — is
    already baked into ``nba_player_teams.csv``, keyed by the same
    ``player_id``. Repeating it here would be two columns that can disagree
    about the same player, and the day the fame formula is retuned only one of
    them would be re-baked. ``apps.questions.career_stats`` joins the two on the
    id instead.
"""

from __future__ import annotations

import csv
import gzip
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

#: The artifact every script in this folder writes one column of.
CAREER_STATS_CSV = (
    REPO_ROOT / "backend" / "apps" / "questions" / "artifacts" / "nba_player_career_stats.csv"
)

#: The columns that say *who* a row is about. Everything else in the header is a
#: stat column owned by one script in this folder.
IDENTITY_COLUMNS = ("player_id", "player_name")


def _teams_bake():
    """``scripts/bake_nba_player_teams.py``, imported as a module.

    Loaded by path rather than by name because ``scripts/`` is a folder of
    runnable scripts, not a package — there is no ``scripts.career_stats``
    import path to reach a sibling through, and making one would mean every
    script here grew a ``-m`` invocation for the sake of one import.
    """
    path = SCRIPTS_DIR / "bake_nba_player_teams.py"
    spec = importlib.util.spec_from_file_location("bake_nba_player_teams", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("bake_nba_player_teams", module)
    spec.loader.exec_module(module)
    return module


teams_bake = _teams_bake()

#: Re-exported so a stat script imports one module and not two.
DEFAULT_TMP = teams_bake.DEFAULT_TMP
cache_seasons = teams_bake.cache_seasons
latest_season_start_year = teams_bake.latest_season_start_year
raw_path = teams_bake.raw_path
season_label = teams_bake.season_label
seasons_to_pull = teams_bake.seasons_to_pull


@dataclass(frozen=True)
class StatSpec:
    """What one script in this folder owns.

    ``column`` is the name the artifact carries and the name a question is
    authored against (``stat: fg3m`` in the YAML), so it is a published contract
    with the people writing questions: renaming one silently retires every
    question that asks about it, exactly as renaming a ``QuestionType`` would.

    ``gamelog_field`` is the box-score column summed to produce it —
    ``stats.nba.com``'s spelling, upper case.

    ``first_season`` is the first season worth pulling. Not a filter on the
    output but on the *requests*: three-pointers before 1979-80 are a column of
    zeros for a shot that did not exist, and eighty requests to confirm that is
    thirty-odd minutes of somebody's afternoon. A stat the league has always
    kept leaves it at the default.
    """

    column: str
    gamelog_field: str
    first_season: int = teams_bake.FIRST_SEASON_START_YEAR

    def __post_init__(self) -> None:
        if self.column in IDENTITY_COLUMNS:
            raise ValueError(f"{self.column!r} is an identity column, not a stat")


# --- Reduce: one season of box scores -> one total per player ----------------


def _season_totals(season: str, *, tmp: Path, spec: StatSpec) -> dict[str, list]:
    """One season's per-player total of ``spec.gamelog_field``, cached in tmp.

    Cached per (stat, season) beside the raw pull for the same reason the teams
    bake caches its reduction: the raw log is ~70MB of gzipped box scores per
    era, and iterating on the bake should not re-read them.
    """
    path = tmp / "career-stats" / spec.column / f"{season}.json"
    if path.exists():
        return json.loads(path.read_text())

    with gzip.open(raw_path(tmp, season), "rt", encoding="utf-8") as handle:
        rows = json.load(handle)

    totals: dict[str, list] = {}
    for row in rows:
        player_id = str(row["PLAYER_ID"])
        # ``or 0`` for the reason the teams bake uses it: a missing stat is one
        # the league did not keep that season, not a zero the player earned, and
        # both read as "adds nothing" to a career total.
        value = row.get(spec.gamelog_field) or 0
        entry = totals.setdefault(player_id, [row["PLAYER_NAME"], 0])
        entry[1] += value

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(totals))
    return totals


def career_totals(seasons: list[str], *, tmp: Path, spec: StatSpec) -> dict[int, tuple[str, int]]:
    """Every player's career total, as ``{player_id: (name, total)}``.

    The name kept is the **last** one the league logged him under, because the
    seasons are rolled up in order and a player who changed the spelling of his
    name (or had it corrected) should appear as the league lists him today.
    """
    totals: dict[int, tuple[str, int]] = {}
    for season in seasons:
        for player_id, (name, value) in _season_totals(season, tmp=tmp, spec=spec).items():
            _, running = totals.get(int(player_id), ("", 0))
            totals[int(player_id)] = (name, running + value)
    return totals


# --- The artifact: read it, add one column, write it back --------------------


def read_artifact(path: Path) -> tuple[list[str], dict[int, dict[str, str]]]:
    """The file as it stands: its column order, and its rows by player id.

    A missing file is the first stat script ever run, which is an ordinary thing
    and not an error — it comes back as an empty artifact with only the identity
    columns.
    """
    if not path.exists():
        return list(IDENTITY_COLUMNS), {}

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or IDENTITY_COLUMNS)
        rows = {int(row["player_id"]): dict(row) for row in reader}
    return columns, rows


def merge_column(
    *, spec: StatSpec, totals: dict[int, tuple[str, int]], path: Path
) -> tuple[int, int]:
    """Write ``spec.column`` into the artifact, leaving every other column alone.

    Three rules, and each is a thing a naive rewrite gets wrong:

    - **A player the artifact already knows keeps his other stats.** The whole
      point of one file is that adding free throws does not drop the threes.
    - **A player this stat has never heard of still gets a cell.** He is left
      empty rather than zeroed: an empty cell means "this script did not measure
      him" (he retired before the three-point line) and a zero means "he took
      the shots and missed", and a question asking for *at most* N would score
      those two the same way if they were written the same way.
    - **The column is refreshed in place**, not appended twice, so re-running a
      script is as idempotent as re-running the loader.

    Returns ``(rows written, rows this column filled)``.
    """
    columns, rows = read_artifact(path)
    if spec.column not in columns:
        columns.append(spec.column)

    for player_id, (name, value) in totals.items():
        row = rows.setdefault(player_id, {"player_id": str(player_id), "player_name": name})
        # The name is refreshed from the pull: the artifact should spell a
        # player the way the league's most recent log does.
        row["player_name"] = name
        row[spec.column] = str(value)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, restval="")
        writer.writeheader()
        # Ordered by the stat just baked, biggest first, then by name: the file
        # is read by a person as often as by the loader, and the top of a column
        # is where an obviously wrong number shows itself.
        writer.writerows(
            sorted(
                rows.values(),
                key=lambda row: (-_as_number(row.get(spec.column)), row["player_name"]),
            )
        )
    return len(rows), len(totals)


def _as_number(value: str | None) -> float:
    """A cell as a number for sorting, with an empty cell sorting last."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


# --- The run itself ----------------------------------------------------------


def bake(spec: StatSpec, argv: list[str] | None = None) -> int:
    """The body of every script in this folder: fetch, sum, merge, report.

    A stat script is its docstring, a :class:`StatSpec` and a call to this —
    which is the shape that makes "expand the artifact with another column" a
    job with no decisions left in it.
    """
    import argparse

    parser = argparse.ArgumentParser(description=f"Bake {spec.column} into {CAREER_STATS_CSV.name}")
    parser.add_argument("--tmp-dir", type=Path, default=DEFAULT_TMP)
    parser.add_argument("--out", type=Path, default=CAREER_STATS_CSV)
    parser.add_argument("--from-season", type=int, default=spec.first_season)
    parser.add_argument("--to-season", type=int, default=latest_season_start_year())
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-fetch seasons already in the raw cache (use it for the season in progress)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="bake from whatever the shared raw cache already holds, issuing no requests",
    )
    args = parser.parse_args(argv)

    seasons = seasons_to_pull(first=args.from_season, last=args.to_season)
    print(f"{spec.column}: {len(seasons)} seasons, {seasons[0]}..{seasons[-1]}")
    print(f"tmp: {args.tmp_dir}  (shared with bake_nba_player_teams.py)")

    if args.offline:
        seasons = [season for season in seasons if raw_path(args.tmp_dir, season).exists()]
        print(f"offline: {len(seasons)} seasons in the cache")
        if not seasons:
            print("Nothing cached to bake from.", file=sys.stderr)
            return 1
    else:
        cache_seasons(seasons, tmp=args.tmp_dir, refresh=args.refresh)

    totals = career_totals(seasons, tmp=args.tmp_dir, spec=spec)
    written, filled = merge_column(spec=spec, totals=totals, path=args.out)

    print(f"\n{filled} players measured, {written} rows -> {args.out}")
    leaders = sorted(totals.items(), key=lambda item: -item[1][1])[:10]
    print(f"\nTop 10 by {spec.column}:")
    for player_id, (name, value) in leaders:
        print(f"  {value:>7}  {name}  (#{player_id})")
    return 0
