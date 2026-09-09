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

from django.db import models

from .base import BaseQuestion, QuestionType


class ColumnsRowsQuestion(BaseQuestion):
    """The grid itself.

    ``row_count``/``column_count`` are stored rather than counted from the child
    rows: they are what the client sizes its grid from before it has fetched
    anything, and the loader checks them against the rows and columns the file
    actually declares, so the two can never disagree.
    """

    row_count = models.PositiveSmallIntegerField()
    column_count = models.PositiveSmallIntegerField()

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
    """The answer at one intersection.

    Cells are **sparse**: the diagonal of a team-versus-team grid has no answer,
    and neither does any pairing nobody has a fact about. A missing cell is a
    cell the player is not asked to fill, which is why the grid is not simply
    ``row_count x column_count`` answers.

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
    answer = models.CharField(max_length=255)

    class Meta:
        ordering = ("row__order", "column__order")
        constraints = [
            models.UniqueConstraint(
                fields=["row", "column"], name="uniq_matrix_cell_per_intersection"
            )
        ]

    def __str__(self) -> str:
        return f"{self.row.title} x {self.column.title} = {self.answer}"
