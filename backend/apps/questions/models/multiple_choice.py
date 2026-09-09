"""Pick one, pick one picture, or pick several.

The three share a shape — a list of options, some of them correct — and are
still three tables. The alternative was one options table with a nullable
``text`` and a nullable ``image``, where every read has to know which of the two
this row actually uses and nothing stops a row having neither.
"""

from __future__ import annotations

from django.db import models

from .base import BaseQuestion, QuestionType


class MultipleChoiceQuestion(BaseQuestion):
    """Anything answered by choosing from options the server supplied.

    Abstract and empty on purpose: it adds no column, it names a family. The
    evaluator for every subclass compares option ids, and grouping them says so.
    """

    class Meta(BaseQuestion.Meta):
        abstract = True


class _Option(models.Model):
    """What every option carries regardless of what it shows.

    ``order`` is the authored order, which is *not* the order a player sees:
    the client shuffles, or the first option would be the answer twice out of
    three times by habit. It exists so the resource file and the admin list a
    question's options the way its author wrote them.
    """

    is_correct = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField()

    class Meta:
        abstract = True
        ordering = ("order",)


class SingleAnswerQuestion(MultipleChoiceQuestion):
    """Four bits of text, one of them right."""

    class Meta(MultipleChoiceQuestion.Meta):
        pass

    @property
    def question_type(self) -> str:
        return QuestionType.SINGLE_ANSWER


class SingleAnswerOption(_Option):
    question = models.ForeignKey(
        SingleAnswerQuestion, on_delete=models.CASCADE, related_name="options"
    )
    text = models.CharField(max_length=255)

    class Meta(_Option.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["question", "order"], name="uniq_single_answer_option_order"
            )
        ]

    def __str__(self) -> str:
        return self.text


class SingleAnswerImageQuestion(MultipleChoiceQuestion):
    """The options are pictures — "which player is this?".

    A separate type from :class:`SingleAnswerQuestion` rather than a flag on it,
    because the client renders a grid of images instead of a list of rows, and a
    question that can be either has no single layout.
    """

    class Meta(MultipleChoiceQuestion.Meta):
        pass

    @property
    def question_type(self) -> str:
        return QuestionType.IMAGE_ANSWER


class ImageAnswerOption(_Option):
    question = models.ForeignKey(
        SingleAnswerImageQuestion, on_delete=models.CASCADE, related_name="options"
    )
    #: Written by ``sync_questions``, which copies the file out of the resource
    #: folder beside the YAML into MEDIA_ROOT. Never uploaded through a form.
    image = models.ImageField(upload_to="questions/answers/")
    #: Alt text, and what the result screen can name the option by. Optional —
    #: a "which player is this" grid may deliberately be captionless.
    label = models.CharField(max_length=255, blank=True)

    class Meta(_Option.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["question", "order"], name="uniq_image_answer_option_order"
            )
        ]

    def __str__(self) -> str:
        return self.label or self.image.name


class MultipleAnswerQuestion(MultipleChoiceQuestion):
    """Several options are right, and the player must find all of them.

    Partial credit is a decision for the evaluator, not for the schema: the row
    records which options are correct, and how a half-right answer scores is
    settled where a match is scored.
    """

    class Meta(MultipleChoiceQuestion.Meta):
        pass

    @property
    def question_type(self) -> str:
        return QuestionType.MULTIPLE_ANSWER


class MultipleAnswerOption(_Option):
    question = models.ForeignKey(
        MultipleAnswerQuestion, on_delete=models.CASCADE, related_name="options"
    )
    text = models.CharField(max_length=255)

    class Meta(_Option.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["question", "order"], name="uniq_multiple_answer_option_order"
            )
        ]

    def __str__(self) -> str:
        return self.text
