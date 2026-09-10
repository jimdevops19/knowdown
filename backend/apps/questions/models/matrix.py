"""A grid: name the thing where a row and a column meet.

    ,                Miami Heat   Phoenix Suns   Lakers
    Miami Heat            -             ?             ?
    Phoenix Suns          ?             -             ?

There is deliberately **one** model for every grid size. 2x2, 2x3 and 3x3 as
separate models would be three copies of the same code differing only in a
number, and a 4x3 would be a fourth; ``row_count``/``column_count`` say the same
thing as data.
"""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .base import BaseQuestion, QuestionType

#: How obscure a cell answer is, as a hand-graded 2..10 scale. A pick everybody
#: makes — Michael Jordan for Bulls x Wizards — is a 2; one only a fan of that
#: roster would reach for is a 10. Authored per answer rather than per cell,
#: because the whole point of holding several answers for one intersection is
#: that they are not equally hard to think of.
MIN_PROBABILITY_SCORE = 2
MAX_PROBABILITY_SCORE = 10

#: What an answer is worth until somebody grades it. Middle of the scale on
#: purpose: an ungraded answer should read as neither obvious nor obscure.
DEFAULT_PROBABILITY_SCORE = 5


class MatrixKind(models.TextChoices):
    """Where a grid's answer key comes from.

    ``AUTHORED`` is the original and the default: every accepted answer is a
    :class:`MatrixCellAnswer` row, written by hand in the resource file. It is
    the only shape that works for a grid whose answers are a judgement — "a
    season this franchise won the title in", "a stat line worth calling out".

    ``TEAMS`` is the grid whose answer key is a *fact* rather than a judgement:
    both axes name NBA franchises and a cell is filled by anybody who played for
    both of them. Its cells hold no answers at all — ``apps.questions.rosters``
    answers them from the baked CSV — because the alternative was tens of
    thousands of authored rows per question, copied again by the next question
    that asked the same thing, and stale the day somebody is traded.

    Stored on the question rather than inferred from "does this grid have
    answers?", because a grid with no answer rows is otherwise exactly what an
    authoring mistake looks like.
    """

    AUTHORED = "authored", "Authored answers"
    TEAMS = "teams", "NBA teams (answers from the roster artifact)"


class ColumnsRowsQuestion(BaseQuestion):
    """The grid itself.

    ``row_count``/``column_count`` are stored rather than counted from the child
    rows: they are what the client sizes its grid from before it has fetched
    anything, and the loader checks them against the rows and columns the file
    actually declares, so the two can never disagree.
    """

    row_count = models.PositiveSmallIntegerField()
    column_count = models.PositiveSmallIntegerField()
    kind = models.CharField(
        max_length=16,
        choices=MatrixKind.choices,
        default=MatrixKind.AUTHORED,
        help_text="Where this grid's accepted answers come from.",
    )

    class Meta(BaseQuestion.Meta):
        pass

    @property
    def question_type(self) -> str:
        return QuestionType.MATRIX


class _Axis(models.Model):
    """A heading down the side or along the top."""

    title = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField()

    class Meta:
        abstract = True
        ordering = ("order",)


class MatrixRow(_Axis):
    question = models.ForeignKey(
        ColumnsRowsQuestion, on_delete=models.CASCADE, related_name="rows"
    )

    class Meta(_Axis.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["question", "order"], name="uniq_matrix_row_order"
            )
        ]

    def __str__(self) -> str:
        return self.title


class MatrixColumn(_Axis):
    question = models.ForeignKey(
        ColumnsRowsQuestion, on_delete=models.CASCADE, related_name="columns"
    )

    class Meta(_Axis.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["question", "order"], name="uniq_matrix_column_order"
            )
        ]

    def __str__(self) -> str:
        return self.title


class MatrixCell(models.Model):
    """An intersection the player is asked to fill.

    Cells are **sparse**: the diagonal of a team-versus-team grid has no answer,
    and neither does any pairing nobody has a fact about. A missing cell is a
    cell the player is not asked to fill, which is why the grid is not simply
    ``row_count x column_count`` answers.

    A cell holds **no answer of its own** — it has :class:`MatrixCellAnswer`
    children, one per thing that counts as right there. "Name a player who
    played for both these teams" has as many right answers as the two rosters
    share, and an ``answer`` column on this row would have made whichever one
    the author thought of first the only one that scores.

    ``question`` is carried alongside ``row``/``column`` even though it is
    reachable through either, because every read is "the cells of this question"
    and the alternative is a join to answer it.
    """

    question = models.ForeignKey(
        ColumnsRowsQuestion, on_delete=models.CASCADE, related_name="cells"
    )
    row = models.ForeignKey(MatrixRow, on_delete=models.CASCADE, related_name="cells")
    column = models.ForeignKey(
        MatrixColumn, on_delete=models.CASCADE, related_name="cells"
    )

    class Meta:
        ordering = ("row__order", "column__order")
        constraints = [
            models.UniqueConstraint(
                fields=["row", "column"], name="uniq_matrix_cell_per_intersection"
            )
        ]

    def __str__(self) -> str:
        return f"{self.row.title} x {self.column.title}"


class MatrixCellAnswer(models.Model):
    """One thing that counts as right at one intersection.

    The sibling of :class:`~apps.questions.models.FreeTextAnswer`, stored the
    same way — as authored, compared case-insensitively at evaluation time —
    with one field of its own: ``probability_score``, how obscure the pick is on
    a 2..10 scale. Nothing scores with it yet (a cell is right or it is not, and
    credit is still per authored *cell*); it is stored rather than derived later
    because it is a judgement about the sport that only an author can make.

    Uniqueness is on the exact spelling, so two spellings of one player
    (``Shaq`` beside ``Shaquille O'Neal``) are legal and deliberate: they are
    two ways to type one right answer, exactly as a free-text question's
    accepted spellings are.
    """

    cell = models.ForeignKey(
        MatrixCell, on_delete=models.CASCADE, related_name="answers"
    )
    value = models.CharField(max_length=255)
    probability_score = models.PositiveSmallIntegerField(
        default=DEFAULT_PROBABILITY_SCORE,
        validators=[
            MinValueValidator(MIN_PROBABILITY_SCORE),
            MaxValueValidator(MAX_PROBABILITY_SCORE),
        ],
        help_text=(
            f"How obscure this pick is: {MIN_PROBABILITY_SCORE} (everybody says "
            f"it) to {MAX_PROBABILITY_SCORE} (deep cut)."
        ),
    )

    class Meta:
        ordering = ("probability_score", "value")
        constraints = [
            models.UniqueConstraint(
                fields=["cell", "value"], name="uniq_matrix_cell_answer_value"
            )
        ]

    def __str__(self) -> str:
        return f"{self.value} ({self.probability_score})"
