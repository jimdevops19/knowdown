"""The numbers the questions domain is measured against.

Level bands live here rather than in ``apps.matches`` because they are a
statement about the *catalog*: a band is a range of difficulty deep enough to
draw a match from, and whether it is deep enough is a question about the
questions. The matchmaker will pick a band for two players by rating; that
choice is the match domain's, and the bands it chooses between are this domain's.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.questions.models import MAX_LEVEL

__all__ = [
    "CATALOG_DEPTH_TARGET",
    "GRADUAL_HINTS_FALLBACK_CLOCK_SECONDS",
    "HINT_ANSWER_WINDOW_SECONDS",
    "LEVEL_BANDS",
    "LONGEST_MATCH_QUESTION_COUNT",
    "LevelBand",
    "band_for_level",
]


@dataclass(frozen=True)
class LevelBand:
    """A contiguous stretch of the 1..``MAX_LEVEL`` difficulty scale."""

    name: str
    low: int
    high: int

    @property
    def level_range(self) -> tuple[int, int]:
        """The pair ``selectors.available_questions`` takes."""
        return self.low, self.high

    def contains(self, level: int) -> bool:
        return self.low <= level <= self.high

    def __str__(self) -> str:
        return f"{self.low}-{self.high}"


#: The bands the matchmaker will draw from.
#:
#: Three, over ten levels — the ten levels exist so a band can be *re-cut* (see
#: ``models.MAX_LEVEL``: three buckets are not enough resolution to pitch a
#: question at a rating), and these three are what the catalog is stocked to
#: today. Widening or splitting a band is a line here plus questions to fill it;
#: it is not a migration, because nothing stores a band — a question stores its
#: level, and a band is a way of reading levels.
LEVEL_BANDS: tuple[LevelBand, ...] = (
    LevelBand("easy", 1, 3),
    LevelBand("medium", 4, 7),
    LevelBand("hard", 8, 10),
)

#: The longest match the platform runs, and so the number of questions a band
#: must hold before it can be played at all.
#:
#: ``apps.matches.constants.MATCH_QUESTION_COUNTS`` will be ``(3, 5, 7)`` and
#: this is its maximum. Stated here rather than imported from there because the
#: catalog has to be measurable without the match engine existing — and because
#: the dependency runs the other way round everywhere else in the platform.
#: When ``matches.constants`` lands, a test asserting the two agree is cheaper
#: than an import that inverts the direction.
LONGEST_MATCH_QUESTION_COUNT = 7

#: The depth a band is *stocked* to, as opposed to the depth it needs to run.
#:
#: Seven questions makes a band playable; seven questions makes it the same
#: seven questions every time. Fifty is the floor at which a player can play a
#: band repeatedly without recognising the board — it is a content target the
#: report names a shortfall against, not a rule anything refuses on, because
#: refusing would take a category out of service for being merely repetitive.
CATALOG_DEPTH_TARGET = 50


#: The least clock a gradual-hints question must have left *after* its final
#: hint lands.
#:
#: A hint schedule that runs to the edge of the time limit is a question whose
#: last clue is decorative — it appears with no time to use it, and the player
#: who was going to get it right anyway has already answered. Ten seconds is
#: the free-text clock (``apps.matches.constants
#: .FALLBACK_QUESTION_TIME_LIMIT_SECONDS``), which is what this is: once the
#: hints have stopped, what is left is a typed answer against a clock.
#:
#: Checked when the file is loaded (``schemas.GradualHintsSpec``), where an
#: over-long schedule is a question an author can still fix, rather than at
#: play time where it is a clue nobody sees.
HINT_ANSWER_WINDOW_SECONDS = 10

#: What a gradual-hints question gets for a clock when it authors no
#: ``time_limit_seconds`` of its own.
#:
#: **Owned by ``apps.matches``**, which is the domain that decides how long a
#: question stays open — this is a *copy*, kept here because the load-time
#: check above needs a number and importing the match engine into the question
#: schemas would invert every other dependency in the platform. Exactly the
#: arrangement ``LONGEST_MATCH_QUESTION_COUNT`` describes above, and it is
#: held to the same standard: ``apps.matches.tests.test_constants`` asserts the
#: two agree, so the copy cannot quietly drift into refusing questions the
#: engine would have been happy to run (or, worse, accepting ones it cuts off).
GRADUAL_HINTS_FALLBACK_CLOCK_SECONDS = 40


def band_for_level(level: int) -> LevelBand:
    """The band a question of this difficulty falls in."""
    for band in LEVEL_BANDS:
        if band.contains(level):
            return band
    raise ValueError(f"Level {level} is outside 1..{MAX_LEVEL}.")


# The bands must tile the scale exactly: a level in no band is a question that
# can never be drawn, and a level in two is a question drawn twice as often.
# Checked at import, so a mis-edit of the tuple above fails the boot rather than
# quietly retiring a stretch of the catalog.
_covered = [level for band in LEVEL_BANDS for level in range(band.low, band.high + 1)]
if _covered != list(range(1, MAX_LEVEL + 1)):
    raise ImportError(
        f"LEVEL_BANDS must tile 1..{MAX_LEVEL} exactly once, ascending; "
        f"got {_covered}."
    )
