"""Name as many as you can — the question whose answer is a *list*.

    "Name as many players as you can with 1,000+ career three-pointers."

    30s   [ Ray Allen ]  ✓        Reggie Miller · Ray Allen · Jason Terry ·
                                  Jamal Crawford · Vince Carter …

Every other type asks for one thing and settles whether you have it. This one
asks how *deep* you can go, and pays accordingly: a player who gets there with
Stephen Curry and James Harden has answered the question, and a player who gets
there with Jason Terry and Danny Green has answered it better.

Three things follow, and each of them is why this is a type rather than a
variant of free text:

**The answer key is not in the database.** It is every player above a line in a
column of a baked CSV (``apps.questions.career_stats``) — hundreds of names,
different tomorrow, and identical to the next question that draws the line
somewhere else. What the question stores is the *line*: a stat, a comparison
and a threshold. Re-baking the artifact updates every question of this type at
once and none of them needs reloading, which is exactly the bargain
``MatrixKind.TEAMS`` strikes for a team grid.

**Credit is earned, not counted.** A name is worth the player's
``probability_score`` — the same 2..10 fame grade the roster artifact carries —
and ``target_score`` is the pile that counts as a full answer. Everywhere else
in this app that score is a *clue* and is hidden (``FORBIDDEN_FIELD_NAMES``);
here it is the point, because a mode that paid the same for every name is a
mode where the winning move is to type the five most famous shooters and stop.

**Nothing is graded while the clock runs.** The player types names into a list
and the whole list is submitted once, as one payload. Scoring name-by-name over
the socket would turn the question into an oracle: type a name, see it light up
green or not, and the server has answered the question for you by the third
guess.
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models

from .base import BaseQuestion, QuestionType

#: The most names one submission may carry. A ceiling on the *payload*, not on
#: the mode: nobody types 200 names in half a minute, and a list that long is a
#: script rather than a player. Generous enough that a real answer never meets
#: it, small enough that the evaluator's work is bounded whatever arrives.
MAX_SUBMITTED_NAMES = 200

#: What a question's ``target_score`` means in the smallest case worth
#: authoring: one obvious name (a 2) plus one that is not. A target under this
#: is a question answered by a reflex, which is a single-answer question.
MIN_TARGET_SCORE = 5


class NameAsManyDataset(models.TextChoices):
    """Which baked artifact the answers come from.

    One member today, and a field rather than a constant for the reason
    ``MatrixKind`` is one: the *shape* of this question — a line drawn through a
    column of numbers — outlives the particular file it is drawn through, and a
    per-season or per-playoff-run dataset is the obvious next one. Stored, so a
    question that predates the second dataset keeps meaning what it meant.
    """

    NBA_CAREER_STATS = "nba-career-stats", "NBA career totals (baked artifact)"


class StatComparison(models.TextChoices):
    """Which side of the line qualifies.

    Two, not six. ``at-least`` asks the question this mode is for — *name the
    players who did a lot of this* — and ``at-most`` asks the inverted one that
    is occasionally worth asking (fewest, worst, least). Strict inequalities are
    deliberately absent: "more than 999" and "at least 1,000" are the same
    question, and offering both is two ways to author one thing plus a chance to
    pick the wrong one.

    The values are the *one* vocabulary: the YAML authors them, the row stores
    them, and ``career_stats.comparison_holds`` compares with them. A second
    spelling of "at least" anywhere would be one typo away from a question
    nobody can answer.
    """

    AT_LEAST = "at-least", "At least"
    AT_MOST = "at-most", "At most"


class NameAsManyQuestion(BaseQuestion):
    """A line through a column of a baked artifact, and what clearing it pays.

    There is no options table and no answers table, which is the whole point:
    every child row this type might have written is a fact already sitting in a
    CSV, and writing them out would make each question carry its own copy of a
    list that goes stale the next time the league plays.
    """

    dataset = models.CharField(
        max_length=32,
        choices=NameAsManyDataset.choices,
        default=NameAsManyDataset.NBA_CAREER_STATS,
        help_text="Which baked artifact the qualifying players come from.",
    )

    #: A column of the artifact — ``fg3m``, and whatever the next bake script
    #: adds. Free text rather than choices because the set of stats is a
    #: property of the *file*, not of this code: a new column is a new script
    #: under ``scripts/career_stats/`` and questions authored against it the
    #: same afternoon, with no migration in between. A stat the artifact does
    #: not carry is refused when the YAML loads (``schemas.NameAsManySpec``).
    stat = models.CharField(
        max_length=60,
        help_text="The artifact column this question draws its line through, e.g. 'fg3m'.",
    )

    comparison = models.CharField(
        max_length=16,
        choices=StatComparison.choices,
        default=StatComparison.AT_LEAST,
    )

    #: Where the line is. A float because a stat column may hold one (a
    #: percentage, a per-game average) even though every column baked so far
    #: holds counts; comparing an integer against a float is exact for every
    #: value either of them can hold here.
    threshold = models.FloatField(
        help_text="The figure a player's stat is compared against.",
    )

    #: The popularity points that count as a **full** answer — the denominator
    #: of this type's credit. Authored per question because it is the only knob
    #: that makes a question easy or hard once the line is drawn: the same
    #: 1,000-threes question is a warm-up at 12 and a specialist's question at
    #: 40. Checked at load time against the points actually on the board, so a
    #: target nobody could reach is a load error rather than a question that
    #: cannot be fully answered.
    target_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(MIN_TARGET_SCORE)],
        help_text=(
            "Popularity points worth full credit. A name pays the player's "
            "2..10 fame grade, so an obvious pick is worth 2 and a deep cut 10."
        ),
    )

    #: The case where the clock *is* the question: "name as many as you can in
    #: thirty seconds" is authored with the number in the prompt, so this and
    #: the words a player reads have to agree. Long enough to be worth typing
    #: into, short enough to stay a race — and a question of this type that
    #: wants a different clock has to say so in its own wording and its own
    #: ``time_limit_seconds`` together.
    DEFAULT_TIME_LIMIT_SECONDS = 30

    class Meta(BaseQuestion.Meta):
        pass

    @property
    def question_type(self) -> str:
        return QuestionType.NAME_AS_MANY
