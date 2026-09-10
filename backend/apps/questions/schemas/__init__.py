"""The shape of the YAML resource files.

Authoring a question is hand-editing a text file, so the failure mode is a typo
— a missing key, two options marked correct, a matrix cell naming a row the file
never declared. These models catch all of it at load time with a message that
names the offending question, rather than letting it reach the database and
surface later as a question nobody can answer.

Everything here is *strict*: unknown keys are rejected rather than ignored, so a
misspelled field is a load error instead of a silent default. The rules live here
rather than as database constraints when they are statements about a whole entry
— "exactly one option is correct", "positions run 1..n with no gaps" — which is
something a per-row constraint cannot see.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.questions.models import MAX_LEVEL, QuestionType


class _Strict(BaseModel):
    """Reject unknown keys — a misspelled field would otherwise load as a
    silent default, and the question would be quietly wrong rather than loudly
    refused.

    Numbers *are* accepted where text is expected, though, because YAML has no
    way to know that ``1991`` in a list of championship years is a label rather
    than an integer. Refusing it would mean every author who writes a year has to
    remember to quote it, and the failure is at load time rather than at review
    time — a rule that costs more than the mistake it prevents.
    """

    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)


class CategorySpec(_Strict):
    """One entry in ``resources/categories.yaml``."""

    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=100)
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    is_active: bool = True


class _QuestionSpec(_Strict):
    """Everything every question carries, whatever its answer shape."""

    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=120)
    description: str = Field(min_length=1)
    level: int = Field(ge=1, le=MAX_LEVEL)
    tags: dict[str, str] = Field(default_factory=dict)
    #: A picture of what is being asked about — a file under the category's
    #: ``images/`` folder. Not the answer options; see ImageOptionSpec for those.
    image: str | None = None
    #: Overrides how long a matchup leaves this question open, in seconds.
    #: Rare — most questions take their type's fallback
    #: (``apps.matches.constants.time_limit_ms_for``) — but an unusually
    #: fiddly question can ask for more without every question of its type
    #: getting it too. Unset (``None``) is the ordinary case.
    time_limit_seconds: int | None = Field(default=None, ge=1, le=600)


class _TextOptionSpec(_Strict):
    text: str = Field(min_length=1, max_length=255)
    is_correct: bool = False


class _ImageOptionSpec(_Strict):
    #: A filename inside the category's ``images/`` folder, not a path: the
    #: loader resolves it, so a resource folder stays movable.
    image: str = Field(min_length=1)
    label: str = ""
    is_correct: bool = False


def _exactly_one_correct(options: list, kind: str, slug: str) -> None:
    correct = [option for option in options if option.is_correct]
    if len(correct) != 1:
        raise ValueError(
            f"{kind} {slug!r} must mark exactly one option correct, found {len(correct)}"
        )


class SingleAnswerSpec(_QuestionSpec):
    """``type: single-answer`` — a list of texts, one of them right."""

    type: Literal[QuestionType.SINGLE_ANSWER]
    options: list[_TextOptionSpec] = Field(min_length=2)

    @model_validator(mode="after")
    def _one_correct(self) -> SingleAnswerSpec:
        _exactly_one_correct(self.options, "single-answer question", self.slug)
        return self


class ImageAnswerSpec(_QuestionSpec):
    """``type: image-answer`` — the options are pictures."""

    type: Literal[QuestionType.IMAGE_ANSWER]
    options: list[_ImageOptionSpec] = Field(min_length=2)

    @model_validator(mode="after")
    def _one_correct(self) -> ImageAnswerSpec:
        _exactly_one_correct(self.options, "image-answer question", self.slug)
        return self

    @model_validator(mode="after")
    def _distinct_images(self) -> ImageAnswerSpec:
        """The same picture twice is a question with two identical buttons, one
        of which is wrong."""
        names = [option.image for option in self.options]
        if len(set(names)) != len(names):
            raise ValueError(
                f"image-answer question {self.slug!r} uses the same image twice"
            )
        return self


class MultipleAnswerSpec(_QuestionSpec):
    """``type: multiple-answer`` — several options are right."""

    type: Literal[QuestionType.MULTIPLE_ANSWER]
    options: list[_TextOptionSpec] = Field(min_length=3)

    @model_validator(mode="after")
    def _at_least_two_correct_and_one_wrong(self) -> MultipleAnswerSpec:
        """Two bounds, and both are about the question being worth asking. With
        one correct option it is a single-answer wearing the wrong type; with
        none wrong, "select all" has one answer — select everything."""
        correct = sum(1 for option in self.options if option.is_correct)
        if correct < 2:
            raise ValueError(
                f"multiple-answer question {self.slug!r} needs at least two correct "
                f"options, found {correct} — a single correct option is a single-answer"
            )
        if correct == len(self.options):
            raise ValueError(
                f"multiple-answer question {self.slug!r} marks every option correct"
            )
        return self


class TrueFalseSpec(_QuestionSpec):
    """``type: true-false``."""

    type: Literal[QuestionType.TRUE_FALSE]
    answer: bool


class FreeTextSpec(_QuestionSpec):
    """``type: free-text`` — every spelling that counts as right."""

    type: Literal[QuestionType.FREE_TEXT]
    accepted_answers: list[str] = Field(min_length=1)

    @field_validator("accepted_answers")
    @classmethod
    def _no_blank_or_duplicate(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("accepted_answers may not contain a blank entry")
        # Compared case-insensitively at evaluation time, so two spellings that
        # differ only in case are one accepted answer written twice.
        folded = [value.casefold() for value in cleaned]
        if len(set(folded)) != len(folded):
            raise ValueError("accepted_answers repeats an answer")
        return cleaned


class OrderingSpec(_QuestionSpec):
    """``type: ordering`` — the items, authored in their correct order.

    Positions are **not** authored: the list order *is* the answer, so there is
    no way to write a file whose positions have a gap or a duplicate. The loader
    numbers them 1..n.
    """

    type: Literal[QuestionType.ORDERING]
    instruction: str = Field(min_length=1)
    items: list[str] = Field(min_length=3)

    @field_validator("items")
    @classmethod
    def _distinct(cls, values: list[str]) -> list[str]:
        if len({value.strip().casefold() for value in values}) != len(values):
            raise ValueError("ordering items must be distinct")
        return [value.strip() for value in values]


class MatrixCellSpec(_Strict):
    row: str = Field(min_length=1)
    column: str = Field(min_length=1)
    answer: str = Field(min_length=1, max_length=255)


class MatrixSpec(_QuestionSpec):
    """``type: matrix`` — headings down the side, along the top, and the cells.

    Cells name their row and column **by title**, not by index, so inserting a
    row at the top of the file does not silently re-target every answer below it.
    ``row_count``/``column_count`` are derived from the headings rather than
    authored, because a count that can disagree with the thing it counts will.
    """

    type: Literal[QuestionType.MATRIX]
    rows: list[str] = Field(min_length=2)
    columns: list[str] = Field(min_length=2)
    cells: list[MatrixCellSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _headings_distinct(self) -> MatrixSpec:
        for axis, titles in (("rows", self.rows), ("columns", self.columns)):
            if len(set(titles)) != len(titles):
                raise ValueError(f"matrix question {self.slug!r} repeats a {axis} title")
        return self

    @model_validator(mode="after")
    def _cells_name_declared_headings(self) -> MatrixSpec:
        """A cell pointing at a heading that is not in the file is an answer
        nobody can reach — and, before this, a silent KeyError at load time."""
        rows, columns = set(self.rows), set(self.columns)
        seen: set[tuple[str, str]] = set()
        for cell in self.cells:
            if cell.row not in rows:
                raise ValueError(
                    f"matrix question {self.slug!r}: cell names undeclared row {cell.row!r}"
                )
            if cell.column not in columns:
                raise ValueError(
                    f"matrix question {self.slug!r}: cell names undeclared column "
                    f"{cell.column!r}"
                )
            if (cell.row, cell.column) in seen:
                raise ValueError(
                    f"matrix question {self.slug!r}: two answers for "
                    f"{cell.row!r} x {cell.column!r}"
                )
            seen.add((cell.row, cell.column))
        return self


#: The discriminated union the loader parses each entry as. ``type`` picks the
#: model, so a wrong key lands as "unknown type" naming the entry rather than as
#: a wall of every variant's errors.
QuestionSpec = Annotated[
    Union[
        SingleAnswerSpec,
        ImageAnswerSpec,
        MultipleAnswerSpec,
        TrueFalseSpec,
        FreeTextSpec,
        OrderingSpec,
        MatrixSpec,
    ],
    Field(discriminator="type"),
]


class QuestionFileSpec(_Strict):
    """One resource file: the category it is for, and its questions.

    The category is stated once per file rather than on every entry — it is a
    property of the folder the file sits in, and repeating it a hundred times is
    a hundred chances to typo it.
    """

    category: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    questions: list[QuestionSpec] = Field(min_length=1)


__all__ = [
    "CategorySpec",
    "FreeTextSpec",
    "ImageAnswerSpec",
    "MatrixCellSpec",
    "MatrixSpec",
    "MultipleAnswerSpec",
    "OrderingSpec",
    "QuestionFileSpec",
    "QuestionSpec",
    "SingleAnswerSpec",
    "TrueFalseSpec",
]
