"""The shape of an answer a player submits.

The sibling of this package's resource schemas, for the other direction. Those
validate a *file* a question author wrote; these validate a *payload* a client
sent, and the difference in provenance is the whole reason they are two modules
rather than one:

- A resource file is trusted content under review, so numbers are coerced to
  text (``1991`` in a list of championship years is a label, not an integer) and
  a mistake is caught in a pull request. A client payload is untrusted input, so
  nothing is coerced that a client could have sent correctly.
- A malformed payload is a **bug in the client**, not a wrong answer. That is
  why these models are strict about shape and say nothing about correctness:
  ``services.evaluation`` turns a parse failure into ``ValidationFailed`` and a
  well-formed-but-wrong answer into a score of zero, and conflating the two
  would let a client farm points by sending nonsense the server scored as an
  honest miss.

What is *not* checked here is anything needing the question: whether an option id
belongs to it, whether an ordering names every item exactly once, whether a
matrix cell is one the player was asked to fill. A payload is a shape; only the
evaluator has the row to check it against.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.questions.models import QuestionType

#: An option id as it travels: the ``BigAutoField`` primary key of one of the
#: option/heading tables, which the play-time serializers emit alongside the text
#: (see ``apps.questions.api.serializers``). Positive because an auto field
#: starts at 1, so ``0`` or a negative is a client that made an id up.
OptionId = Annotated[int, Field(gt=0)]


class _StrictSubmission(BaseModel):
    """Reject unknown keys.

    A payload carrying a field the server does not read is a client written
    against a contract that no longer exists — or one hoping the server reads
    something it should not. Both are worth refusing loudly: step 10's rule that
    a client-submitted ``response_time_ms`` is never trusted is enforced here, by
    the payload carrying no such field and an extra one being an error rather
    than something quietly dropped.
    """

    model_config = ConfigDict(extra="forbid")


class _OneOptionSubmission(_StrictSubmission):
    """Pick exactly one of the options the server sent."""

    option_id: OptionId


class SingleAnswerSubmission(_OneOptionSubmission):
    type: Literal[QuestionType.SINGLE_ANSWER]


class ImageAnswerSubmission(_OneOptionSubmission):
    """Same payload as :class:`SingleAnswerSubmission`, and still its own type.

    The discriminator has to agree with the question's own
    :attr:`~apps.questions.models.BaseQuestion.question_type`, or a client could
    answer an image question with a payload built for a text one — harmless
    today, and exactly the kind of leniency that hides a client bug until the two
    types stop having the same shape.
    """

    type: Literal[QuestionType.IMAGE_ANSWER]


class MultipleAnswerSubmission(_StrictSubmission):
    """Every option the player believes is correct, and no others.

    At least one id: an empty set is not a submission. A player who ran out of
    time submits nothing at all, and that path is the question timing out
    (``matches.complete_question``), not an answer with no picks in it.
    """

    type: Literal[QuestionType.MULTIPLE_ANSWER]
    option_ids: list[OptionId] = Field(min_length=1)

    @field_validator("option_ids")
    @classmethod
    def _distinct(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values):
            raise ValueError("option_ids names the same option twice")
        return values


class TrueFalseSubmission(_StrictSubmission):
    type: Literal[QuestionType.TRUE_FALSE]
    answer: bool


class FreeTextSubmission(_StrictSubmission):
    """What the player typed, as they typed it.

    Kept verbatim rather than normalised on the way in: the comparison is the
    evaluator's business, and a recorded answer should be the thing the player
    can be shown afterwards, not a casefolded key they never wrote. The length
    cap matches ``FreeTextAnswer.value`` — an answer longer than any accepted
    spelling cannot be one.
    """

    type: Literal[QuestionType.FREE_TEXT]
    text: str = Field(min_length=1, max_length=255)


class OrderingSubmission(_StrictSubmission):
    """The options in the order the player put them, first to last.

    The whole sequence, not the moves that produced it: the server holds the
    correct positions and compares the arrangement, so there is no partial state
    to keep between submissions. Whether the list names every item exactly once
    needs the question, so the evaluator checks it.
    """

    type: Literal[QuestionType.ORDERING]
    option_ids: list[OptionId] = Field(min_length=1)

    @field_validator("option_ids")
    @classmethod
    def _distinct(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values):
            raise ValueError("option_ids places the same option twice")
        return values


class MatrixCellSubmission(_StrictSubmission):
    """One filled-in intersection.

    Names its row and column **by id**, unlike the resource file's cells which
    name them by title: the client was sent ids, and matching a title back would
    make a player's answer depend on the exact spelling of a heading.
    """

    row_id: OptionId
    column_id: OptionId
    answer: str = Field(min_length=1, max_length=255)


class MatrixSubmission(_StrictSubmission):
    """The cells the player filled in — not necessarily all of them.

    A grid is scored per cell (see ``services.evaluation``), so a partly filled
    submission is a partly right answer rather than a malformed one. What *is*
    malformed is two answers for one intersection, because then there is no
    single thing the player said.
    """

    type: Literal[QuestionType.MATRIX]
    cells: list[MatrixCellSubmission] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_answer_per_intersection(self) -> MatrixSubmission:
        seen = {(cell.row_id, cell.column_id) for cell in self.cells}
        if len(seen) != len(self.cells):
            raise ValueError("cells gives two answers for the same intersection")
        return self


#: The discriminated union a submitted payload is parsed as. ``type`` picks the
#: model — the same discriminator, drawn from the same
#: :class:`~apps.questions.models.QuestionType`, as the resource union — so a
#: payload naming a type the platform does not have fails as "unknown type"
#: rather than as every variant's errors at once.
AnswerSubmission = Annotated[
    Union[
        SingleAnswerSubmission,
        ImageAnswerSubmission,
        MultipleAnswerSubmission,
        TrueFalseSubmission,
        FreeTextSubmission,
        OrderingSubmission,
        MatrixSubmission,
    ],
    Field(discriminator="type"),
]

#: Every submission model, by the question type it answers. The sibling of
#: ``models.QUESTION_MODELS`` and ``services.evaluation.ANSWER_EVALUATORS``,
#: keyed the same way: adding a question type means adding a line to each, and a
#: test walks all three to make sure none was forgotten.
ANSWER_SUBMISSIONS: dict[str, type[_StrictSubmission]] = {
    QuestionType.SINGLE_ANSWER: SingleAnswerSubmission,
    QuestionType.IMAGE_ANSWER: ImageAnswerSubmission,
    QuestionType.MULTIPLE_ANSWER: MultipleAnswerSubmission,
    QuestionType.TRUE_FALSE: TrueFalseSubmission,
    QuestionType.FREE_TEXT: FreeTextSubmission,
    QuestionType.ORDERING: OrderingSubmission,
    QuestionType.MATRIX: MatrixSubmission,
}

__all__ = [
    "ANSWER_SUBMISSIONS",
    "AnswerSubmission",
    "FreeTextSubmission",
    "ImageAnswerSubmission",
    "MatrixCellSubmission",
    "MatrixSubmission",
    "MultipleAnswerSubmission",
    "OptionId",
    "OrderingSubmission",
    "SingleAnswerSubmission",
    "TrueFalseSubmission",
]
