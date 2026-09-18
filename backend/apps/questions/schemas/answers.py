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

from apps.questions.models import MAX_SUBMITTED_NAMES, QuestionType

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


class GradualHintsFieldSubmission(_StrictSubmission):
    """One box, filled in.

    Names its field **by id**, not by label, for the reason a matrix cell names
    its row and column by id: the client was sent ids, and matching a label back
    would make a player's answer depend on the exact spelling of a heading.
    """

    field_id: OptionId
    text: str = Field(min_length=1, max_length=255)


class GradualHintsSubmission(_StrictSubmission):
    """The fields the player filled in — not necessarily all of them.

    Scored per field (see ``services.evaluation``), so a partly filled
    submission is a partly right answer rather than a malformed one; the
    sibling of :class:`MatrixSubmission` in this and in what it refuses, which
    is two answers for one field, because then there is no single thing the
    player said.

    A field left blank is simply absent. There is no "I do not know" value to
    send, and an empty string is refused rather than treated as one: an answer
    is something the player typed.
    """

    type: Literal[QuestionType.GRADUAL_HINTS]
    answer_fields: list[GradualHintsFieldSubmission] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_answer_per_field(self) -> GradualHintsSubmission:
        if len({field.field_id for field in self.answer_fields}) != len(
            self.answer_fields
        ):
            raise ValueError("answer_fields gives two answers for the same field")
        return self


class NameAsManySubmission(_StrictSubmission):
    """Every name the player listed, as they typed them.

    **One payload, not one per name.** The board accumulates names locally and
    sends the list once, which is what keeps the server from being an oracle: a
    client that submitted each name as it was typed would be handed a verdict
    per guess, and three guesses in, the question would have answered itself.
    The engine's one-answer-per-question rule (``matches.services
    .submit_answer`` is idempotent) is the other half of the same guarantee.

    Kept verbatim for the reason :class:`FreeTextSubmission` is: what is
    recorded should be the thing the player can be shown afterwards, and the
    folding is the evaluator's business.

    Two names that fold to the same thing are **malformed**, not a repeat worth
    zero: the board de-duplicates as the player types, so a list containing one
    name twice is a client that stopped doing that — the sibling of a matrix
    payload answering one intersection twice.
    """

    type: Literal[QuestionType.NAME_AS_MANY]
    names: list[str] = Field(min_length=1, max_length=MAX_SUBMITTED_NAMES)

    @field_validator("names")
    @classmethod
    def _non_blank(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("names may not contain a blank entry")
        if any(len(value) > 255 for value in values):
            raise ValueError("names may not contain an entry longer than 255 characters")
        return values

    @model_validator(mode="after")
    def _each_name_once(self) -> NameAsManySubmission:
        folded = {" ".join(name.split()).casefold() for name in self.names}
        if len(folded) != len(self.names):
            raise ValueError("names lists the same name twice")
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
        GradualHintsSubmission,
        NameAsManySubmission,
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
    QuestionType.GRADUAL_HINTS: GradualHintsSubmission,
    QuestionType.NAME_AS_MANY: NameAsManySubmission,
}

__all__ = [
    "ANSWER_SUBMISSIONS",
    "AnswerSubmission",
    "FreeTextSubmission",
    "GradualHintsFieldSubmission",
    "GradualHintsSubmission",
    "ImageAnswerSubmission",
    "MatrixCellSubmission",
    "MatrixSubmission",
    "MultipleAnswerSubmission",
    "NameAsManySubmission",
    "OptionId",
    "OrderingSubmission",
    "SingleAnswerSubmission",
    "TrueFalseSubmission",
]
