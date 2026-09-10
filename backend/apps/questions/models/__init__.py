"""The question models, and the registry that holds them together.

Each answer shape is its own table (see ``base.BaseQuestion`` for why), so
nothing in Django relates them to each other. :data:`QUESTION_MODELS` is what
does: the loader iterates it to know which model a YAML ``type:`` belongs to, the
selectors iterate it to draw a matchup's questions from every shape at once, and
the admin iterates it to register them. Adding a question type means adding a
model, a :class:`QuestionType` member, a schema and **one line here** — and
anything that walks the registry picks it up for free.
"""

from __future__ import annotations

from .base import MAX_LEVEL, BaseQuestion, QuestionType
from .free_text import FreeTextAnswer, FreeTextQuestion, TrueFalseQuestion
from .matrix import (
    DEFAULT_PROBABILITY_SCORE,
    MAX_PROBABILITY_SCORE,
    MIN_PROBABILITY_SCORE,
    ColumnsRowsQuestion,
    MatrixCell,
    MatrixCellAnswer,
    MatrixColumn,
    MatrixKind,
    MatrixRow,
)
from .multiple_choice import (
    ImageAnswerOption,
    MultipleAnswerOption,
    MultipleAnswerQuestion,
    MultipleChoiceQuestion,
    SingleAnswerImageQuestion,
    SingleAnswerOption,
    SingleAnswerQuestion,
)
from .ordering import OrderingOption, OrderingQuestion

#: Every concrete question model, by the type key it is authored under.
QUESTION_MODELS: dict[str, type[BaseQuestion]] = {
    QuestionType.SINGLE_ANSWER: SingleAnswerQuestion,
    QuestionType.IMAGE_ANSWER: SingleAnswerImageQuestion,
    QuestionType.MULTIPLE_ANSWER: MultipleAnswerQuestion,
    QuestionType.TRUE_FALSE: TrueFalseQuestion,
    QuestionType.FREE_TEXT: FreeTextQuestion,
    QuestionType.ORDERING: OrderingQuestion,
    QuestionType.MATRIX: ColumnsRowsQuestion,
}

__all__ = [
    "DEFAULT_PROBABILITY_SCORE",
    "MAX_LEVEL",
    "MAX_PROBABILITY_SCORE",
    "MIN_PROBABILITY_SCORE",
    "QUESTION_MODELS",
    "BaseQuestion",
    "ColumnsRowsQuestion",
    "FreeTextAnswer",
    "FreeTextQuestion",
    "ImageAnswerOption",
    "MatrixCell",
    "MatrixCellAnswer",
    "MatrixColumn",
    "MatrixKind",
    "MatrixRow",
    "MultipleAnswerOption",
    "MultipleAnswerQuestion",
    "MultipleChoiceQuestion",
    "OrderingOption",
    "OrderingQuestion",
    "QuestionType",
    "SingleAnswerImageQuestion",
    "SingleAnswerOption",
    "SingleAnswerQuestion",
    "TrueFalseQuestion",
]
