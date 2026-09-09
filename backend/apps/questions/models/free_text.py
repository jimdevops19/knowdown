"""Answers the player supplies rather than picks."""

from __future__ import annotations

from django.db import models

from .base import BaseQuestion, QuestionType


class TrueFalseQuestion(BaseQuestion):
    """The whole answer is one boolean, so there is no options table at all.

    Worth stating because the temptation is to model it as a two-option
    single-answer: that would make "true" a row with an id, and two questions
    would then have different ids for the same word.
    """

    answer = models.BooleanField()

    class Meta(BaseQuestion.Meta):
        pass

    @property
    def question_type(self) -> str:
        return QuestionType.TRUE_FALSE


class FreeTextQuestion(BaseQuestion):
    """The player types it. Correctness is a set of accepted spellings."""

    class Meta(BaseQuestion.Meta):
        pass

    @property
    def question_type(self) -> str:
        return QuestionType.FREE_TEXT


class FreeTextAnswer(models.Model):
    """One spelling that counts as right.

    A question has as many of these as there are honest ways to say the answer —
    ``Kobe Bryant``, ``Kobe``, ``Bryant`` — because a player racing a clock types
    the short one. Stored as authored and compared case-insensitively at
    evaluation time, so the resource file stays readable rather than being a list
    of lowercase keys.
    """

    question = models.ForeignKey(
        FreeTextQuestion, on_delete=models.CASCADE, related_name="accepted_answers"
    )
    value = models.CharField(max_length=255)

    class Meta:
        ordering = ("value",)
        constraints = [
            models.UniqueConstraint(
                fields=["question", "value"], name="uniq_free_text_answer_value"
            )
        ]

    def __str__(self) -> str:
        return self.value
