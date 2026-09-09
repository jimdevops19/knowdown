"""Put these in the right order."""

from __future__ import annotations

from django.db import models

from .base import BaseQuestion, QuestionType


class OrderingQuestion(BaseQuestion):
    """"Rank these players by career points."

    ``instruction`` is separate from ``description`` because the two say
    different things and the client shows them in different places: the
    description is the question, the instruction is the rule for answering it
    ("highest to lowest"). Fold them together and the direction of the sort ends
    up buried in a sentence the UI truncates.
    """

    instruction = models.TextField()

    class Meta(BaseQuestion.Meta):
        pass

    @property
    def question_type(self) -> str:
        return QuestionType.ORDERING


class OrderingOption(models.Model):
    """One item to be placed, and where it belongs.

    The backend stores the correct order and the client shuffles what it draws —
    the server never sends the answer in the shape of the question. Positions are
    1-based and contiguous, checked when the file is loaded rather than by a
    constraint, because "no gaps" is a statement about the whole set and a
    per-row constraint cannot see it.
    """

    question = models.ForeignKey(
        OrderingQuestion, on_delete=models.CASCADE, related_name="options"
    )
    text = models.CharField(max_length=255)
    correct_position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("correct_position",)
        constraints = [
            models.UniqueConstraint(
                fields=["question", "correct_position"],
                name="uniq_ordering_option_position",
            )
        ]

    def __str__(self) -> str:
        return f"{self.correct_position}. {self.text}"
