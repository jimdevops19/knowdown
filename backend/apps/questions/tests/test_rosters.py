"""The baked roster artifact, and the index built over it.

Two separable subjects, tested apart: whether the index answers "who played for
all of these?" correctly (built over a tiny fixture CSV, so a case can name its
own players), and whether the *real* artifact is loadable and says what a grid
authored against it needs it to say.
"""

from __future__ import annotations

import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from apps.questions.rosters import TEAM_ROSTERS_CSV, load_rosters

#: Two namesakes and one well-travelled player. ``Chris Johnson`` appears twice
#: with different ids, which is the case a name-keyed index gets wrong.
FIXTURE_ROWS = [
    (1, "Dennis Rodman", 3, "Chicago Bulls|Los Angeles Lakers"),
    (2, "Chris Johnson", 8, "Boston Celtics"),
    (3, "Chris Johnson", 9, "Memphis Grizzlies"),
    (4, "Émile Fictif", 10, "Chicago Bulls"),
]


def write_fixture(folder: Path, rows=FIXTURE_ROWS) -> Path:
    path = folder / "rosters.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["player_id", "player_name", "probability_score", "teams"])
        writer.writerows(rows)
    return path


class RosterIndexTests(SimpleTestCase):
    def setUp(self) -> None:
        self._folder = TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.index = load_rosters(write_fixture(Path(self._folder.name)))

    def test_a_player_of_both_teams_played_for_both(self) -> None:
        self.assertTrue(
            self.index.played_for_all(
                name="Dennis Rodman", titles=("Chicago Bulls", "Los Angeles Lakers")
            )
        )

    def test_a_player_of_one_team_did_not_play_for_both(self) -> None:
        self.assertFalse(
            self.index.played_for_all(
                name="Émile Fictif", titles=("Chicago Bulls", "Los Angeles Lakers")
            )
        )

    def test_a_name_nobody_has_played_for_nobody(self) -> None:
        self.assertFalse(
            self.index.played_for_all(
                name="Nobody At All", titles=("Chicago Bulls", "Los Angeles Lakers")
            )
        )

    def test_two_players_of_one_name_are_two_people(self) -> None:
        """The reason the index is keyed on player id.

        One Chris Johnson played for Boston and a different one for Memphis;
        neither played for both, and a set of *names* per team would have said
        they did.
        """
        self.assertFalse(
            self.index.played_for_all(
                name="Chris Johnson", titles=("Boston Celtics", "Memphis Grizzlies")
            )
        )
        self.assertTrue(
            self.index.played_for_all(name="Chris Johnson", titles=("Boston Celtics",))
        )

    def test_a_name_is_folded_the_way_every_typed_answer_is(self) -> None:
        self.assertTrue(
            self.index.played_for_all(
                name="  dennis   RODMAN ",
                titles=("Chicago Bulls", "Los Angeles Lakers"),
            )
        )

    def test_a_franchise_is_recognised_however_it_is_capitalised(self) -> None:
        self.assertEqual(
            self.index.canonical_team("los angeles  lakers"), "Los Angeles Lakers"
        )

    def test_a_franchise_that_does_not_exist_has_no_canonical_spelling(self) -> None:
        self.assertIsNone(self.index.canonical_team("LA Lakers"))

    def test_an_unknown_franchise_has_no_players_rather_than_raising(self) -> None:
        """A question that somehow reached scoring with one must score its cells
        wrong, not accept whatever was typed into them."""
        self.assertEqual(self.index.players_for_all(("LA Lakers",)), frozenset())

    def test_a_missing_artifact_is_an_error_not_an_empty_index(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_rosters(Path(self._folder.name) / "not-baked.csv")


class BakedArtifactTests(SimpleTestCase):
    """The real CSV, which every ``kind: teams`` question in ``resources/``
    is authored against."""

    def setUp(self) -> None:
        self.index = load_rosters()

    def test_it_holds_every_current_franchise(self) -> None:
        for title in ("Chicago Bulls", "Los Angeles Lakers", "Miami Heat"):
            self.assertIsNotNone(self.index.canonical_team(title), title)

    def test_it_knows_a_player_who_wore_two_of_those_shirts(self) -> None:
        self.assertTrue(
            self.index.played_for_all(
                name="LeBron James", titles=("Miami Heat", "Los Angeles Lakers")
            )
        )

    def test_it_does_not_invent_one(self) -> None:
        self.assertFalse(
            self.index.played_for_all(
                name="LeBron James", titles=("Chicago Bulls", "Miami Heat")
            )
        )

    def test_it_is_parsed_once_per_path(self) -> None:
        """A megabyte of CSV, read on the first question that wants it and not
        again — a re-read per answer would put file I/O in the middle of a
        race."""
        self.assertIs(load_rosters(), load_rosters(TEAM_ROSTERS_CSV))
