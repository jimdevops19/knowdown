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

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.questions.career_stats import load_career_stats
from apps.questions.constants import (
    DEFAULT_TIME_LIMIT_SECONDS,
    HINT_ANSWER_WINDOW_SECONDS,
)
from apps.questions.models import (
    DEFAULT_HINT_INTERVAL_SECONDS,
    AnswerFieldKind,
    DEFAULT_PROBABILITY_SCORE,
    MAX_ANSWER_FIELDS,
    MAX_HINT_INTERVAL_SECONDS,
    MAX_HINTS,
    MAX_LEVEL,
    MAX_PROBABILITY_SCORE,
    MIN_PROBABILITY_SCORE,
    MIN_TARGET_SCORE,
    MatrixKind,
    NameAsManyDataset,
    QuestionType,
    StatComparison,
)
from apps.questions.matching import normalise_answer
from apps.questions.rosters import load_rosters


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
    #: Rare — a question ordinarily takes the clock its *file* sets
    #: (``QuestionFileSpec.time_limit_seconds``) — but an unusually fiddly
    #: entry can ask for more without every question beside it getting it too.
    #: Unset (``None``) is the ordinary case, and the loader fills it in from
    #: the file before anything is written.
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


def _no_blank_or_duplicate_answers(values: list[str], *, field_name: str) -> list[str]:
    """The rule ``accepted_answers`` obeys, wherever it is authored.

    Two types write that key — ``free-text``, where it is the whole answer, and
    ``gradual-hints``, where each field has its own — and both are compared
    case-insensitively at evaluation time, so both have to refuse the same two
    mistakes: a blank entry, and two spellings that differ only in case (which
    is one accepted answer written twice).
    """
    cleaned = [value.strip() for value in values]
    if any(not value for value in cleaned):
        raise ValueError(f"{field_name} may not contain a blank entry")
    folded = [value.casefold() for value in cleaned]
    if len(set(folded)) != len(folded):
        raise ValueError(f"{field_name} repeats an answer")
    return cleaned


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
        return _no_blank_or_duplicate_answers(values, field_name="accepted_answers")


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


#: What a ``kind: number`` field's accepted answers may look like: digits, with
#: an optional sign and decimal part. Deliberately narrow — a thousands
#: separator or a range ("60-70") is a *text* answer that happens to be about
#: numbers, and the point of the check is to catch the field that says "number"
#: over a box wanting "Game 7".
_NUMERIC_ANSWER = re.compile(r"^[+-]?\d+(\.\d+)?$")


class GradualHintsFieldSpec(_Strict):
    """One box the player types into, and everything that fills it."""

    label: str = Field(min_length=1, max_length=60)
    #: Text or number. Sizes the box and picks the phone keyboard
    #: (``models.AnswerFieldKind``); it does not change what counts as right.
    #: Defaulted rather than required because a box is a text box unless the
    #: author has a reason, and the reason is worth one word in the file.
    kind: AnswerFieldKind = AnswerFieldKind.TEXT
    accepted_answers: list[str] = Field(min_length=1)

    @field_validator("accepted_answers")
    @classmethod
    def _no_blank_or_duplicate(cls, values: list[str]) -> list[str]:
        return _no_blank_or_duplicate_answers(values, field_name="accepted_answers")

    @model_validator(mode="after")
    def _a_number_field_accepts_numbers(self) -> GradualHintsFieldSpec:
        """A box drawn six characters wide must not want ``Game 7`` typed into it.

        The kind is a promise to the player — this one is short, here is a
        number pad — and the only way to break it is to mark a field ``number``
        and then key it to words. Checked here because it is a *file* mistake:
        nothing at play time would notice, and the player would meet a box their
        answer does not fit.
        """
        wrong = [value for value in self.accepted_answers if not _NUMERIC_ANSWER.match(value)]
        if self.kind == AnswerFieldKind.NUMBER and wrong:
            raise ValueError(
                f"answer field {self.label!r} is kind: number but accepts "
                f"{wrong[0]!r} — drop the kind, or key it to a number"
            )
        return self


class GradualHintsSpec(_QuestionSpec):
    """``type: gradual-hints`` — a question, clues on a timer, and boxes to fill.

    ``hints`` is authored **hardest first**: the list order is the reveal order,
    so hint one goes out the moment the clock starts and each of the others one
    ``hint_interval_seconds`` after the last. Positions are not authored, for
    the reason no position in this app is — the list order is the schedule, so a
    file cannot have a gap in it.

    ``answer_fields`` is what the player fills in, and each field is graded on
    its own (``services.evaluation``). Every field carries every spelling that
    fills it, the same way a free-text question does: somebody racing a clock
    types ``7``, not ``Game 7``.
    """

    type: Literal[QuestionType.GRADUAL_HINTS]
    hints: list[str] = Field(min_length=1, max_length=MAX_HINTS)
    #: How long one hint is up before the next joins it. Per question, because
    #: it is a property of the clues: five one-line stat clues want a tighter
    #: spacing than three clues each of which is a sentence to read.
    hint_interval_seconds: int = Field(
        default=DEFAULT_HINT_INTERVAL_SECONDS, ge=1, le=MAX_HINT_INTERVAL_SECONDS
    )
    answer_fields: list[GradualHintsFieldSpec] = Field(
        min_length=1, max_length=MAX_ANSWER_FIELDS
    )

    @field_validator("hints")
    @classmethod
    def _no_blank_or_duplicate_hints(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("hints may not contain a blank entry")
        # The same clue twice is a reveal that stalls: the player waits out an
        # interval for something they have already read.
        folded = [value.casefold() for value in cleaned]
        if len(set(folded)) != len(folded):
            raise ValueError("hints repeats a hint")
        return cleaned

    @model_validator(mode="after")
    def _field_labels_distinct(self) -> GradualHintsSpec:
        """Two boxes with one label is a board the player cannot read, and an
        answer nobody can check by eye against the file."""
        labels = [field.label.strip().casefold() for field in self.answer_fields]
        if len(set(labels)) != len(labels):
            raise ValueError(
                f"gradual-hints question {self.slug!r} repeats an answer field label"
            )
        return self

    def check_the_clock_outlasts_the_schedule(self) -> None:
        """The last hint must land with time left to use it.

        Not a validator of its own, because the answer depends on a number
        this entry may not carry: the clock is authored here
        (``time_limit_seconds``) or, far more often, once at the top of the
        file — so the check can only run after ``QuestionFileSpec`` has handed
        the file's clock down, and that is where it is called from.

        Nothing at play time would notice the two disagreeing: the question
        would simply close on a player still waiting for a clue that was never
        going to arrive. So it is checked at load, against whichever clock this
        question will actually get, and the fix is one line either way — fewer
        hints, a tighter interval, or a ``time_limit_seconds`` that covers it.
        """
        last_hint_at = (len(self.hints) - 1) * self.hint_interval_seconds
        clock = self.time_limit_seconds or DEFAULT_TIME_LIMIT_SECONDS
        if clock - last_hint_at < HINT_ANSWER_WINDOW_SECONDS:
            raise ValueError(
                f"gradual-hints question {self.slug!r}: the last of its "
                f"{len(self.hints)} hints lands at {last_hint_at}s of a {clock}s "
                f"question, leaving under {HINT_ANSWER_WINDOW_SECONDS}s to answer "
                f"— shorten the schedule or raise time_limit_seconds"
            )


class MatrixAnswerSpec(_Strict):
    """One thing that counts as right at one intersection.

    Written either in full::

        {answer: Michael Jordan, probability_score: 2}

    or as a bare string, which is the same entry graded
    ``DEFAULT_PROBABILITY_SCORE``. The shorthand exists because a cell with a
    single obvious answer is common and a three-key mapping to say so is noise;
    the long form exists because ``probability_score`` is a judgement about the
    sport, and the point of it is that an author sets it by hand.
    """

    answer: str = Field(min_length=1, max_length=255)
    probability_score: int = Field(
        default=DEFAULT_PROBABILITY_SCORE,
        ge=MIN_PROBABILITY_SCORE,
        le=MAX_PROBABILITY_SCORE,
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_a_bare_string(cls, value):
        return {"answer": value} if isinstance(value, str) else value


class MatrixCellSpec(_Strict):
    """One intersection, and **every** answer that fills it.

    ``answers`` is a list because most interesting grids have more than one
    right answer per square — "a player who played for both these teams" is
    satisfied by everybody the two rosters share — and a single ``answer:``
    string would have made whichever name the author thought of first the only
    one that scores.
    """

    row: str = Field(min_length=1)
    column: str = Field(min_length=1)
    answers: list[MatrixAnswerSpec] = Field(min_length=1)

    @field_validator("answers")
    @classmethod
    def _no_duplicate_answers(
        cls, values: list[MatrixAnswerSpec]
    ) -> list[MatrixAnswerSpec]:
        # Compared case-insensitively for the same reason free-text spellings
        # are: the evaluator folds case, so two entries differing only in it are
        # one answer written twice — with, worse, two different grades.
        folded = [value.answer.strip().casefold() for value in values]
        if len(set(folded)) != len(folded):
            raise ValueError("cell repeats an answer")
        return values


class MatrixSpec(_QuestionSpec):
    """``type: matrix`` — headings down the side, along the top, and the cells.

    Cells name their row and column **by title**, not by index, so inserting a
    row at the top of the file does not silently re-target every answer below it.
    ``row_count``/``column_count`` are derived from the headings rather than
    authored, because a count that can disagree with the thing it counts will.

    ``kind`` chooses where the answers come from. The default writes them out;
    ``kind: teams`` names two axes of NBA franchises and takes them from
    ``apps.questions.rosters`` instead, cells and all — see ``models.MatrixKind``
    for why that is a question type's worth of difference rather than a
    convenience.
    """

    type: Literal[QuestionType.MATRIX]
    #: Where the answer key comes from — see ``models.MatrixKind``. The default
    #: is the authored grid, so every question written before this existed means
    #: what it always did.
    kind: MatrixKind = MatrixKind.AUTHORED
    rows: list[str] = Field(min_length=2)
    columns: list[str] = Field(min_length=2)
    #: Empty for ``kind: teams``, where the grid is derived rather than written:
    #: the loader fills in every intersection the two rosters actually share.
    cells: list[MatrixCellSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _authored_grids_author_their_cells(self) -> MatrixSpec:
        """``cells`` is required for an authored grid and refused for a derived
        one.

        Refused rather than merged: a file that both declares ``kind: teams``
        and writes out three cells is an author who believes one of the two is
        in charge, and guessing which would make the other silently do nothing.
        """
        if self.kind == MatrixKind.AUTHORED and not self.cells:
            raise ValueError(
                f"matrix question {self.slug!r}: an authored grid needs at least one cell"
            )
        if self.kind != MatrixKind.AUTHORED and self.cells:
            raise ValueError(
                f"matrix question {self.slug!r}: a {self.kind.value!r} grid derives its "
                f"cells, so it may not author them"
            )
        return self

    @model_validator(mode="after")
    def _team_headings_name_real_franchises(self) -> MatrixSpec:
        """Every heading of a ``kind: teams`` grid must be a franchise the
        roster artifact knows.

        Caught here rather than at evaluation time, where a mistyped
        ``"LA Lakers"`` would be a column no answer can fill and a player would
        find out with the clock running. Names are matched the way a typed
        answer is — folded — so the file may spell a franchise however reads
        best; only a franchise that does not exist is an error.
        """
        if self.kind != MatrixKind.TEAMS:
            return self
        rosters = load_rosters()
        unknown = [
            title
            for title in [*self.rows, *self.columns]
            if rosters.canonical_team(title) is None
        ]
        if unknown:
            raise ValueError(
                f"matrix question {self.slug!r}: {', '.join(repr(t) for t in unknown)} "
                f"name no NBA franchise in the roster artifact"
            )

        # A grid nobody can fill in anywhere is not a hard question, it is a
        # broken one — and it is a mistake only the artifact can catch, since
        # both axes are perfectly well-spelled franchises that simply never
        # shared a player. Individual empty intersections are fine and expected:
        # the grid is sparse, and the loader writes only the cells that have
        # somebody in them.
        if not any(
            rosters.players_for_all((row, column))
            for row in self.rows
            for column in self.columns
            if normalise_answer(row) != normalise_answer(column)
        ):
            raise ValueError(
                f"matrix question {self.slug!r}: no two of these franchises ever "
                f"shared a player, so the grid has no cell anybody could fill"
            )
        return self

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


class NameAsManySpec(_QuestionSpec):
    """``type: name-as-many`` — a line through a column of a baked artifact.

    The whole question is five fields, and **no answer key at all**::

        - type: name-as-many
          slug: nba-1000-career-threes
          description: Name as many players as you can with 1,000+ career threes.
          level: 5
          time_limit_seconds: 30
          stat: fg3m
          comparison: at-least
          threshold: 1000
          target_score: 24

    Who qualifies is a fact in ``artifacts/nba_player_career_stats.csv``, read
    at scoring time (``apps.questions.career_stats``) — so re-baking the
    artifact after last night's games updates every question of this type at
    once, and none of them is reloaded for it. The bargain ``kind: teams``
    strikes for a grid, struck again for a list.

    ``target_score`` is the only difficulty knob once the line is drawn: a name
    pays the player's 2..10 fame grade, and this is the pile that counts as a
    complete answer. Twelve is four or five obvious names; forty is a
    specialist's question. Both of the things that can go wrong with it are
    load errors — see below.
    """

    type: Literal[QuestionType.NAME_AS_MANY]
    #: Which artifact the qualifying players come from. One dataset today, and
    #: authored rather than assumed for the reason ``kind`` is on a matrix: a
    #: question written now must keep meaning what it meant when the second
    #: dataset arrives.
    dataset: NameAsManyDataset = NameAsManyDataset.NBA_CAREER_STATS
    #: A stat column of the artifact. Checked against the file below, because a
    #: mistyped column is otherwise a question where nothing anybody types is
    #: right and the clock is the first thing to notice.
    stat: str = Field(min_length=1, max_length=60)
    comparison: StatComparison = StatComparison.AT_LEAST
    threshold: float
    target_score: int = Field(ge=MIN_TARGET_SCORE)

    @model_validator(mode="after")
    def _the_line_is_one_somebody_can_clear(self) -> NameAsManySpec:
        """Three refusals, all of them mistakes the file can still fix.

        A **stat the artifact does not carry** is a typo or a question written
        ahead of the bake script that would answer it; either way it is a
        question with no right answers, and the fix is one word here or one run
        of a script in ``scripts/career_stats/``.

        A **line nobody clears** is the same mistake with the threshold rather
        than the column — 100,000 career threes is a perfectly well-formed
        question that no player has ever answered.

        A **target above the points on the board** is the subtler one: the
        question is answerable but not *completely* answerable, so nobody can
        ever be marked correct on it however deep they go. Checked here because
        it is arithmetic over the artifact, which the author cannot do by eye.
        """
        stats = load_career_stats()
        if not stats.has_stat(self.stat):
            raise ValueError(
                f"name-as-many question {self.slug!r}: {self.stat!r} is not a stat in the "
                f"career stats artifact. It carries: {', '.join(stats.stats) or '(none)'} "
                f"— bake another with a script in scripts/career_stats/."
            )

        qualifiers = stats.qualifiers(
            stat=self.stat, comparison=self.comparison, threshold=self.threshold
        )
        if not qualifiers.players:
            raise ValueError(
                f"name-as-many question {self.slug!r}: no player has {self.stat} "
                f"{self.comparison.value} {self.threshold:g}, so the question has no "
                f"right answer"
            )
        if self.target_score > qualifiers.total_score:
            raise ValueError(
                f"name-as-many question {self.slug!r}: target_score "
                f"{self.target_score} is more than the {qualifiers.total_score} points "
                f"on the board ({len(qualifiers.players)} qualifying players), so nobody "
                f"could ever complete it"
            )
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
        GradualHintsSpec,
        NameAsManySpec,
    ],
    Field(discriminator="type"),
]


class QuestionFileSpec(_Strict):
    """One resource file: the category it is for, its clock, and its questions.

    The category is stated once per file rather than on every entry — it is a
    property of the folder the file sits in, and repeating it a hundred times is
    a hundred chances to typo it.

    So is the clock, and for a stronger reason. A resource file is a file of
    *one answer shape* (``free-text.yaml``, ``matrix.yaml``), and how long it
    takes to answer one of these is a property of the shape — twenty seconds to
    type a name, sixty to read a grid, ten to glance at four buttons. Authored
    here rather than as a constant on the model, because it is a judgement
    about the questions, revisable by whoever is writing them, in the file they
    are already editing — and a number that lived in Python could not be tuned
    without a deploy.
    """

    category: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    #: How long every question in this file stays open, unless the entry names
    #: its own. Optional: a file that says nothing leaves its questions on
    #: ``constants.DEFAULT_TIME_LIMIT_SECONDS``, the ordinary
    #: glance-and-answer clock.
    time_limit_seconds: int | None = Field(default=None, ge=1, le=600)
    questions: list[QuestionSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _hand_the_file_clock_down(self) -> QuestionFileSpec:
        """Fill the file's clock into every entry that named none, here rather
        than at write time, so everything downstream — the loader, the
        schedule check below, an error message quoting the number — reads one
        resolved value instead of each re-deciding the fallback.
        """
        if self.time_limit_seconds is not None:
            for question in self.questions:
                if question.time_limit_seconds is None:
                    question.time_limit_seconds = self.time_limit_seconds
        return self

    @model_validator(mode="after")
    def _hint_schedules_fit_their_clocks(self) -> QuestionFileSpec:
        """Checked after the clock is handed down, never before: a
        gradual-hints entry that authors no ``time_limit_seconds`` is answered
        by its file, and validating it against the floor first would refuse a
        schedule the file has already paid for.
        """
        for question in self.questions:
            if isinstance(question, GradualHintsSpec):
                question.check_the_clock_outlasts_the_schedule()
        return self


__all__ = [
    "CategorySpec",
    "FreeTextSpec",
    "GradualHintsFieldSpec",
    "GradualHintsSpec",
    "ImageAnswerSpec",
    "MatrixAnswerSpec",
    "MatrixCellSpec",
    "MatrixSpec",
    "MultipleAnswerSpec",
    "NameAsManySpec",
    "OrderingSpec",
    "QuestionFileSpec",
    "QuestionSpec",
    "SingleAnswerSpec",
    "TrueFalseSpec",
]
