"""Bake `backend/apps/questions/artifacts/nba_player_teams.csv`: every player in
NBA history, every franchise he played for, and how obvious a pick he is.

    uv run python scripts/bake_nba_player_teams.py

WHY THIS IS ONE REQUEST PER SEASON
    The obvious way to ask "which teams did this player play for" is
    ``playercareerstats`` — and that is one request per player, ~5,000 of them,
    which at any rate limit polite enough to survive is hours of pulling. The
    league-wide player game log answers the same question from the other side:
    one request per *season* returns every player-game played in it, carrying
    the player and the team he wore that night. Eighty requests instead of five
    thousand, and it reaches back to 1946-47, which the modern dashboards
    (``leaguedashplayerstats``) do not — they start at 1996-97.

RATE LIMITS
    stats.nba.com throttles hard and without warning, so: one request at a time,
    a fixed floor of RATE_LIMIT_SECONDS between them plus jitter, exponential
    backoff on failure, and — the part that matters most — **every response is
    cached to a tmp file before anything is derived from it**. A re-run reads
    the cache and issues no requests at all, so iterating on the scoring costs
    nothing, and a run interrupted halfway resumes where it stopped.

THE THREE STAGES, EACH LANDING IN TMP FIRST
    1. fetch    one gzipped JSON per season, exactly as the API returned it
                (TMP_DIR/raw/gamelog-<season>.json.gz)
    2. reduce   per season, aggregate the box scores into one row per
                (player, team) (TMP_DIR/reduced/<season>.json)
                ~70MB of gzipped box scores becomes ~6MB of totals, so
                everything downstream re-runs in a second
    3. bake     roll the seasons together, score every player, write the CSV
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import random
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from nba_api.stats.endpoints import leaguegamelog
from requests.exceptions import RequestException

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "backend" / "apps" / "questions" / "artifacts"
DEFAULT_TMP = Path(tempfile.gettempdir()) / "knowdown-nba"

#: The first season the league played, and so the first the game log has.
FIRST_SEASON_START_YEAR = 1946

#: Seconds between two requests, floor. Deliberately generous: this script is
#: run rarely and cached aggressively, so there is nothing to buy by pushing it
#: — and a 429 from stats.nba.com is answered with a silent block, not a header.
RATE_LIMIT_SECONDS = 3.0
JITTER_SECONDS = 1.5
REQUEST_TIMEOUT = 120
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = 15


# --- Stage 1: fetch ----------------------------------------------------------


def season_label(start_year: int) -> str:
    """1996 -> "1996-97"."""
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def seasons_to_pull(*, first: int, last: int) -> list[str]:
    return [season_label(year) for year in range(first, last + 1)]


def latest_season_start_year(today: date | None = None) -> int:
    """The most recent season that has had games played in it.

    A season is named for the year it starts in, tips off in October and runs to
    June, so anything before October belongs to the season that started the year
    before. Pulling a season that has not tipped off yet is harmless — it comes
    back empty — but it costs a request and caches an empty file that a later
    run would trust, so the cutoff is October rather than the off-season.
    """
    today = today or date.today()
    return today.year if today.month >= 10 else today.year - 1


class RateLimiter:
    """One request at a time, never closer together than the floor.

    Jittered because a perfectly regular cadence is itself a signature, and the
    thing being avoided here is being mistaken for a scraper worth blocking.
    """

    def __init__(self, *, seconds: float, jitter: float) -> None:
        self.seconds = seconds
        self.jitter = jitter
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            delay = self.seconds + random.uniform(0, self.jitter)
            slept = time.monotonic() - self._last
            if slept < delay:
                time.sleep(delay - slept)
        self._last = time.monotonic()


def fetch_season(season: str, *, limiter: RateLimiter) -> list[dict]:
    """Every player-game of one season, with retries and backoff.

    Raises after :data:`MAX_ATTEMPTS`, because a season silently missing from
    the middle of the catalog is a player whose career quietly loses a team.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        limiter.wait()
        try:
            response = leaguegamelog.LeagueGameLog(
                season=season,
                player_or_team_abbreviation="P",
                season_type_all_star="Regular Season",
                timeout=REQUEST_TIMEOUT,
            )
            return response.get_normalized_dict()["LeagueGameLog"]
        except (RequestException, KeyError, ValueError) as error:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"{season}: gave up after {attempt} attempts") from error
            pause = BACKOFF_SECONDS * 2 ** (attempt - 1)
            print(f"  {season}: {type(error).__name__}, retrying in {pause}s", file=sys.stderr)
            time.sleep(pause)
    raise AssertionError("unreachable")


def raw_path(tmp: Path, season: str) -> Path:
    return tmp / "raw" / f"gamelog-{season}.json.gz"


def cache_seasons(seasons: list[str], *, tmp: Path, refresh: bool) -> None:
    """Fill the raw cache. The only stage that touches the network."""
    limiter = RateLimiter(seconds=RATE_LIMIT_SECONDS, jitter=JITTER_SECONDS)
    (tmp / "raw").mkdir(parents=True, exist_ok=True)

    for season in seasons:
        path = raw_path(tmp, season)
        if path.exists() and not refresh:
            continue
        rows = fetch_season(season, limiter=limiter)
        # Written through a temporary name: a run killed mid-write must not
        # leave a half-file that the next run trusts and reads back short.
        partial = path.with_suffix(".partial")
        with gzip.open(partial, "wt", encoding="utf-8") as handle:
            json.dump(rows, handle)
        partial.replace(path)
        print(f"  {season}: {len(rows):>6} player-games cached")


# --- Stage 2: reduce ---------------------------------------------------------

#: What a box score line contributes, beyond the points everybody counts. Not a
#: real efficiency metric and not trying to be — it is a *fame* proxy, and fame
#: follows volume: the players nobody can name are the ones who did little of
#: anything, whatever their rate stats said.
CONTRIBUTION_WEIGHTS = {"PTS": 1.0, "REB": 0.5, "AST": 0.8, "STL": 1.2, "BLK": 1.2}


def reduce_season(season: str, *, tmp: Path) -> dict:
    """One raw season -> one row per (player, team), cached in tmp.

    Reduced separately from the bake so the raw box scores are read once and
    everything downstream works from a tenth of the bytes.
    """
    path = tmp / "reduced" / f"{season}.json"
    if path.exists():
        return json.loads(path.read_text())

    with gzip.open(raw_path(tmp, season), "rt", encoding="utf-8") as handle:
        rows = json.load(handle)

    stints: dict[tuple[int, int], dict] = {}
    for row in rows:
        key = (row["PLAYER_ID"], row["TEAM_ID"])
        stint = stints.setdefault(
            key,
            {
                "player_id": row["PLAYER_ID"],
                "player_name": row["PLAYER_NAME"],
                "team_id": row["TEAM_ID"],
                "team_name": row["TEAM_NAME"],
                "team_abbreviation": row["TEAM_ABBREVIATION"],
                "games": 0,
                "points": 0.0,
                "contribution": 0.0,
            },
        )
        stint["games"] += 1
        stint["points"] += row.get("PTS") or 0
        # ``or 0`` throughout: the early seasons have no steals, blocks or
        # rebounds at all, and a missing stat is a stat the league did not keep,
        # not a zero the player earned. Both read as "adds nothing" here, which
        # is the only honest thing a single career number can do with them.
        stint["contribution"] += sum(
            weight * (row.get(stat) or 0) for stat, weight in CONTRIBUTION_WEIGHTS.items()
        )

    reduced = {"season": season, "stints": list(stints.values())}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reduced))
    return reduced


# --- Stage 3: score and bake -------------------------------------------------

#: The 2..10 scale the questions domain grades a matrix answer on
#: (``apps.questions.models.matrix``): 2 is the name everybody says, 10 is the
#: one only somebody who watched that roster reaches for.
MIN_PROBABILITY_SCORE = 2
MAX_PROBABILITY_SCORE = 10

#: Where each score band ends, as a share of all players ordered by fame. Front
#: loaded on purpose: "famous" is a much smaller club than "played in the NBA",
#: so the bands at the obvious end are narrow and the last one — the players a
#: quiz can only use as a deep cut — is by far the widest.
#:
#: Tuned against known anchors, printed by --calibrate: LeBron James and Michael
#: Jordan land on 2, Ray Allen on 3, Mario Chalmers mid-table, Brian Scalabrine
#: on 10.
SCORE_BANDS = (
    (2, 0.009),
    (3, 0.020),
    (4, 0.038),
    (5, 0.065),
    (6, 0.105),
    (7, 0.170),
    (8, 0.260),
    (9, 0.395),
    (10, 1.000),
)

#: Names checked on every run, with the score each is expected to come out at.
#:
#: The two ends are the calibration, not observations: LeBron James and Michael
#: Jordan are what a 2 *means*, Brian Scalabrine is what a 10 means, and
#: :data:`SCORE_BANDS` was cut to put them exactly there. The rest are
#: regression pins — recorded because they came out sensibly, and worth being
#: told about if they move, since a change to the fame formula that reorders the
#: middle of the league is a change worth noticing rather than shipping.
CALIBRATION_ANCHORS = {
    "LeBron James": 2,
    "Michael Jordan": 2,
    "Kobe Bryant": 2,
    "Shaquille O'Neal": 2,
    "Ray Allen": 3,
    "Rashard Lewis": 5,
    "Mario Chalmers": 7,
    "Matthew Dellavedova": 9,
    "Brian Scalabrine": 10,
}


@dataclass
class Player:
    player_id: int
    name: str
    games: int = 0
    points: float = 0.0
    contribution: float = 0.0
    seasons: set[str] = field(default_factory=set)
    #: The seasons he wore each jersey, keyed by ``(franchise id, name)`` — by
    #: the **name**, not the franchise alone, because a franchise that moved
    #: kept its id and changed everything a quiz cares about. Kevin Durant
    #: played for the Seattle SuperSonics and for the Oklahoma City Thunder;
    #: keyed by id he played for one team with two names, and the Sonics
    #: disappear from the file entirely.
    teams: dict[tuple[int, str], dict] = field(default_factory=dict)

    @property
    def stints(self) -> list[dict]:
        """Every jersey he wore, in the order he first wore it."""
        return sorted(self.teams.values(), key=lambda team: team["first_season"])

    @property
    def team_names(self) -> list[str]:
        """Every distinct name he played under, in career order."""
        names: list[str] = []
        for team in self.stints:
            if team["name"] not in names:
                names.append(team["name"])
        return names

    @property
    def fame(self) -> float:
        """Career volume, leant on by rate.

        Volume is the honest part of fame — a long, productive career is the
        thing that makes a name recognisable — but volume alone under-rates the
        short brilliant career (Bill Walton, Yao Ming) and over-rates the
        journeyman who lasted fifteen seasons doing very little. The per-game
        term is what separates those two, and it is deliberately the smaller
        factor of the two.
        """
        per_game = self.contribution / self.games if self.games else 0.0
        return (self.contribution**0.75) * (per_game**0.45)


def build_players(seasons: list[str], *, tmp: Path) -> dict[int, Player]:
    players: dict[int, Player] = {}
    for season in seasons:
        for stint in reduce_season(season, tmp=tmp)["stints"]:
            player = players.setdefault(
                stint["player_id"],
                Player(player_id=stint["player_id"], name=stint["player_name"]),
            )
            player.games += stint["games"]
            player.points += stint["points"]
            player.contribution += stint["contribution"]
            player.seasons.add(season)
            team = player.teams.setdefault(
                (stint["team_id"], stint["team_name"]),
                {
                    "name": stint["team_name"],
                    "abbreviation": stint["team_abbreviation"],
                    "first_season": season,
                    "seasons": set(),
                    "games": 0,
                },
            )
            team["seasons"].add(season)
            team["games"] += stint["games"]
    return players


def season_runs(seasons: set[str]) -> str:
    """Seasons at one franchise, as the unbroken spells they were played in.

    ``2003-04..2009-10, 2014-15..2017-18`` rather than one range from the first
    season to the last: a player who left and came back — LeBron James in
    Cleveland, every second journeyman — otherwise reads as having been there
    the whole time, which is exactly the kind of thing a question would be
    written around and get wrong.
    """
    years = sorted(int(season[:4]) for season in seasons)
    runs: list[list[int]] = []
    for year in years:
        if runs and year == runs[-1][-1] + 1:
            runs[-1][-1] = year
        else:
            runs.append([year, year])
    return ", ".join(
        season_label(start) if start == end else f"{season_label(start)}..{season_label(end)}"
        for start, end in runs
    )


def score_players(players: list[Player]) -> dict[int, int]:
    """Rank by fame, then cut the ranking into the 2..10 bands.

    Ranked rather than thresholded on the raw number, because the raw number is
    not comparable across eras — a 1950s season is 68 games of a game nobody
    kept steals for — and because the question the score answers is relative
    anyway: *of everybody who ever played, how obvious a pick is this one?*
    """
    ordered = sorted(players, key=lambda player: player.fame, reverse=True)
    total = len(ordered)
    scores: dict[int, int] = {}
    for rank, player in enumerate(ordered):
        share = (rank + 1) / total
        scores[player.player_id] = next(
            score for score, ceiling in SCORE_BANDS if share <= ceiling
        )
    return scores


def write_csv(players: list[Player], scores: dict[int, int], *, path: Path) -> None:
    """One row per player, teams pipe-separated.

    A row per player rather than per player-team: the question this file exists
    to answer is "who played for both X and Y", which is a scan of one column,
    and the per-stint detail that a row-per-team would give is in
    ``team_stints`` beside it — ``Miami Heat (2010-11..2013-14)`` — for when a
    question wants a decade rather than a franchise.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(players, key=lambda player: (-player.fame, player.name))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "player_id",
                "player_name",
                "probability_score",
                "teams",
                "team_count",
                "team_stints",
                "first_season",
                "last_season",
                "seasons_played",
                "games_played",
                "points",
            ]
        )
        for player in ordered:
            writer.writerow(
                [
                    player.player_id,
                    player.name,
                    scores[player.player_id],
                    "|".join(player.team_names),
                    len(player.team_names),
                    "|".join(
                        f"{team['name']} ({season_runs(team['seasons'])})"
                        for team in player.stints
                    ),
                    min(player.seasons),
                    max(player.seasons),
                    len(player.seasons),
                    player.games,
                    int(player.points),
                ]
            )


def report_calibration(players: list[Player], scores: dict[int, int]) -> None:
    """Print the anchors, and say so loudly when one has drifted."""
    by_name = {player.name: player for player in players}
    ordered = sorted(players, key=lambda player: player.fame, reverse=True)
    rank_of = {player.player_id: rank + 1 for rank, player in enumerate(ordered)}

    print("\nCalibration anchors (expected -> actual):")
    drifted = []
    for name, expected in CALIBRATION_ANCHORS.items():
        player = by_name.get(name)
        if player is None:
            print(f"  {name:<24} MISSING from the pull")
            drifted.append(name)
            continue
        actual = scores[player.player_id]
        flag = "" if actual == expected else "   <- drifted"
        print(
            f"  {name:<24} {expected} -> {actual}"
            f"  (rank {rank_of[player.player_id]} of {len(ordered)}){flag}"
        )
        if actual != expected:
            drifted.append(name)

    counts = defaultdict(int)
    for score in scores.values():
        counts[score] += 1
    print("\nPlayers per score:")
    for score in range(MIN_PROBABILITY_SCORE, MAX_PROBABILITY_SCORE + 1):
        print(f"  {score:>2}: {counts[score]:>5}")
    if drifted:
        print(f"\n{len(drifted)} anchor(s) off: {', '.join(drifted)}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tmp-dir", type=Path, default=DEFAULT_TMP)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--from-season", type=int, default=FIRST_SEASON_START_YEAR)
    parser.add_argument("--to-season", type=int, default=latest_season_start_year())
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-fetch seasons already in the raw cache (they are immutable once "
        "the season is over — use this only for the season in progress)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="bake from whatever the cache already holds, issuing no requests",
    )
    args = parser.parse_args()

    seasons = seasons_to_pull(first=args.from_season, last=args.to_season)
    print(f"{len(seasons)} seasons, {seasons[0]}..{seasons[-1]}")
    print(f"tmp: {args.tmp_dir}")

    if args.offline:
        seasons = [s for s in seasons if raw_path(args.tmp_dir, s).exists()]
        print(f"offline: {len(seasons)} seasons in the cache")
    else:
        cache_seasons(seasons, tmp=args.tmp_dir, refresh=args.refresh)

    players_by_id = build_players(seasons, tmp=args.tmp_dir)
    players = list(players_by_id.values())
    scores = score_players(players)

    out = args.out_dir / "nba_player_teams.csv"
    write_csv(players, scores, path=out)
    print(f"\n{len(players)} players -> {out}")
    report_calibration(players, scores)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
