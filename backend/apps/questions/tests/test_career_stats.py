"""The baked career-stats artifact, and the index built over it.

The sibling of ``test_rosters.py`` and split the same way: whether the index
answers "who clears this line, and what is naming them worth?" correctly (over a
pair of tiny fixture CSVs, so a case can name its own players), and whether the
*real* artifact is loadable and says what the shipped questions need it to say.

The two-file join is the thing worth testing hardest here. A career total comes
from one artifact and the popularity that prices it comes from another, they are
joined on ``player_id``, and every way that can go wrong — a player in one file
and not the other, two players with one name, an empty cell that is not a zero —
is a question that pays the wrong number rather than one that crashes.
"""

from __future__ import annotations

import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from apps.questions.career_stats import CAREER_STATS_CSV, load_career_stats
from apps.questions.models import DEFAULT_PROBABILITY_SCORE, StatComparison
from apps.questions.rosters import TEAM_ROSTERS_CSV, load_rosters

#: ``player_id, name, fg3m``. The empty cell is the case that matters most: a
#: player the stat was never measured for is **absent from the column**, not a
#: zero in it, so an ``at-most`` question must not accept him.
STAT_ROWS = [
    (1, "Ray Fictif", "2000"),
    (2, "Chris Johnson", "1200"),
    (3, "Chris Johnson", "40"),
    (4, "Émile Fictif", "900"),
    (5, "Bob Beforethreepoint", ""),
    (6, "Unknown Toroster", "1500"),
]

#: The roster artifact this is joined against. Everybody but player 6, who is
#: the "in one file and not the other" case.
ROSTER_ROWS = [
    (1, "Ray Fictif", 3, "Boston Celtics"),
    (2, "Chris Johnson", 8, "Boston Celtics"),
    (3, "Chris Johnson", 9, "Memphis Grizzlies"),
    (4, "Émile Fictif", 10, "Chicago Bulls"),
    (5, "Bob Beforethreepoint", 7, "Chicago Bulls"),
]


def write_fixtures(folder: Path) -> tuple[Path, Path]:
    stats = folder / "career-stats.csv"
    with stats.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["player_id", "player_name", "fg3m"])
        writer.writerows(STAT_ROWS)

    rosters = folder / "rosters.csv"
    with rosters.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["player_id", "player_name", "probability_score", "teams"])
        writer.writerows(ROSTER_ROWS)
    return stats, rosters


class CareerStatsIndexTests(SimpleTestCase):
    def setUp(self) -> None:
        self._folder = TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        stats, rosters = write_fixtures(Path(self._folder.name))
        self.index = load_career_stats(stats, rosters_path=rosters)

    def qualifiers(self, threshold: float, comparison=StatComparison.AT_LEAST):
        return self.index.qualifiers(
            stat="fg3m", comparison=comparison, threshold=threshold
        )

    def test_the_stat_columns_are_whatever_the_file_carries(self) -> None:
        """The whole reason a new stat needs no code: the columns are data."""
        self.assertEqual(self.index.stats, ("fg3m",))
        self.assertTrue(self.index.has_stat("fg3m"))
        self.assertFalse(self.index.has_stat("ftm"))

    def test_at_least_takes_everybody_on_or_above_the_line(self) -> None:
        names = {player.name for player in self.qualifiers(1200).players}
        self.assertEqual(names, {"Ray Fictif", "Chris Johnson", "Unknown Toroster"})

    def test_at_most_takes_everybody_on_or_below_it(self) -> None:
        names = {
            player.name
            for player in self.qualifiers(1000, StatComparison.AT_MOST).players
        }
        self.assertEqual(names, {"Chris Johnson", "Émile Fictif"})

    def test_a_player_the_stat_never_measured_is_on_neither_side(self) -> None:
        """An empty cell is "not measured", which is not a zero.

        Bob retired before the three-point line existed. A file that wrote him
        in as 0 would have him qualify for every "fewest threes" question ever
        asked, which is a wrong answer dressed as a deep cut.
        """
        every_player = {
            player.name
            for player in self.qualifiers(10**9, StatComparison.AT_MOST).players
        }
        self.assertNotIn("Bob Beforethreepoint", every_player)

    def test_a_name_is_priced_by_the_roster_artifact(self) -> None:
        found = self.qualifiers(1200).find("ray fictif")
        self.assertIsNotNone(found)
        self.assertEqual(found.probability_score, 3)

    def test_a_player_missing_from_the_roster_bake_is_still_worth_something(self) -> None:
        """Ungraded, not unpaid — an answer that is right has to pay."""
        found = self.qualifiers(1200).find("Unknown Toroster")
        self.assertEqual(found.probability_score, DEFAULT_PROBABILITY_SCORE)

    def test_namesakes_resolve_to_the_one_who_cleared_the_line(self) -> None:
        """Two Chris Johnsons, one of whom qualifies.

        A name-keyed index that picked the wrong one would mark a right answer
        wrong — and the player who typed it has no way to say which one they
        meant, because a person typing a name means whichever of them the
        question is about.
        """
        found = self.qualifiers(1000).find("Chris Johnson")
        self.assertEqual(found.id, 2)
        self.assertEqual(found.value, 1200)

    def test_a_name_nobody_has_qualifies_for_nothing(self) -> None:
        self.assertIsNone(self.qualifiers(1000).find("Somebody Else"))

    def test_an_unknown_stat_qualifies_nobody_rather_than_raising(self) -> None:
        """The load-time check is what refuses a mistyped stat; reaching
        evaluation with one must score every name wrong, not 500."""
        empty = self.index.qualifiers(
            stat="nosuchstat", comparison=StatComparison.AT_LEAST, threshold=1
        )
        self.assertEqual(empty.players, ())
        self.assertEqual(empty.total_score, 0)

    def test_a_folded_name_matches_the_way_every_typed_answer_does(self) -> None:
        # Émile clears 900, not 1,000 — the line is the subject of another test.
        self.assertIsNotNone(self.qualifiers(900).find("  ÉMILE   fictif ".upper()))

    def test_the_qualifying_list_is_most_obvious_first(self) -> None:
        scores = [player.probability_score for player in self.qualifiers(0).players]
        self.assertEqual(scores, sorted(scores))

    def test_total_score_is_every_point_on_the_board(self) -> None:
        qualifiers = self.qualifiers(1200)
        self.assertEqual(
            qualifiers.total_score,
            sum(player.probability_score for player in qualifiers.players),
        )


class RealArtifactTests(SimpleTestCase):
    """The shipped CSV, as the shipped questions need it to be.

    Thin on purpose — the numbers change every time the bake runs, so anything
    asserted here has to be true of *any* honest re-bake. What must hold is that
    the file is there, that it joins to the roster artifact at all, and that the
    line the catalog draws has enough players behind it to be a question.
    """

    def setUp(self) -> None:
        self.index = load_career_stats()

    def test_the_artifact_is_loadable_and_carries_three_pointers(self) -> None:
        self.assertTrue(CAREER_STATS_CSV.exists(), CAREER_STATS_CSV)
        self.assertIn("fg3m", self.index.stats)

    def test_the_shipped_question_has_a_board_worth_asking(self) -> None:
        """``resources/nba/name-as-many.yaml`` draws its line at 1,000."""
        qualifiers = self.index.qualifiers(
            stat="fg3m", comparison=StatComparison.AT_LEAST, threshold=1000
        )
        self.assertGreater(len(qualifiers.players), 50)
        self.assertGreater(qualifiers.total_score, 24)  # the authored target

    def test_the_obvious_names_are_the_cheap_ones(self) -> None:
        """The join is doing its job if fame and price agree at the top.

        Not a calibration test — that is the bake script's ``--calibrate``. It
        asserts the *direction*: if Stephen Curry ever costs more than the
        median qualifier, the two artifacts have stopped being joined on the
        same ids and every question of this type is quietly mispriced.
        """
        qualifiers = self.index.qualifiers(
            stat="fg3m", comparison=StatComparison.AT_LEAST, threshold=1000
        )
        curry = qualifiers.find("Stephen Curry")
        self.assertIsNotNone(curry)
        median = sorted(player.probability_score for player in qualifiers.players)[
            len(qualifiers.players) // 2
        ]
        self.assertLess(curry.probability_score, median)

    def test_it_is_joined_to_the_roster_artifact_by_id(self) -> None:
        rosters = load_rosters(TEAM_ROSTERS_CSV)
        qualifiers = self.index.qualifiers(
            stat="fg3m", comparison=StatComparison.AT_LEAST, threshold=2000
        )
        for player in qualifiers.players[:10]:
            self.assertEqual(
                player.probability_score, rosters.player(player.id).probability_score
            )
