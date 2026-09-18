"""Question rows, built directly.

The loader has its own suite (``test_sync``); everything else wants *a question
of this shape* in as few lines as possible, and going through YAML to get one
would make every evaluator test a loader test too — so a break in the loader
would fail all of them and say nothing about which.

Every builder takes the same knobs (``slug``, ``level``, ``category``) and
returns a saved question with its children, numbered the way the loader numbers
them: options in list order, ordering positions 1..n. That similarity is what
lets the evaluator and serializer suites be table-driven over
``QUESTION_MODELS`` instead of naming eight shapes twice each.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from apps.categories.models import Category
from apps.questions.models import (
    AnswerFieldKind,
    DEFAULT_PROBABILITY_SCORE,
    ColumnsRowsQuestion,
    FreeTextAnswer,
    FreeTextQuestion,
    GradualHint,
    GradualHintsField,
    GradualHintsFieldAnswer,
    GradualHintsQuestion,
    ImageAnswerOption,
    MatrixCell,
    MatrixCellAnswer,
    MatrixColumn,
    MatrixKind,
    MatrixRow,
    MultipleAnswerOption,
    MultipleAnswerQuestion,
    NameAsManyQuestion,
    OrderingOption,
    OrderingQuestion,
    QuestionType,
    SingleAnswerImageQuestion,
    SingleAnswerOption,
    SingleAnswerQuestion,
    StatComparison,
    TrueFalseQuestion,
)


def make_category(slug: str = "nba", name: str = "NBA", **fields) -> Category:
    category, _ = Category.objects.get_or_create(
        slug=slug, defaults={"name": name, **fields}
    )
    return category


def _base(slug: str, level: int, category: Category | None) -> dict:
    return {
        "slug": slug,
        "description": "A question.",
        "level": level,
        "category": category or make_category(),
    }


def make_single_answer(
    *,
    slug: str = "single",
    level: int = 3,
    category: Category | None = None,
    options: tuple[tuple[str, bool], ...] = (
        ("Boston Celtics", True),
        ("Los Angeles Lakers", False),
        ("Chicago Bulls", False),
    ),
) -> SingleAnswerQuestion:
    question = SingleAnswerQuestion.objects.create(**_base(slug, level, category))
    for order, (text, is_correct) in enumerate(options, start=1):
        SingleAnswerOption.objects.create(
            question=question, text=text, is_correct=is_correct, order=order
        )
    return question


def make_image_answer(
    *,
    slug: str = "images",
    level: int = 2,
    category: Category | None = None,
    options: tuple[tuple[str, bool], ...] = (
        ("court-a.png", True),
        ("court-b.png", False),
    ),
) -> SingleAnswerImageQuestion:
    """The image files are never written.

    An ``ImageField`` holds a path, and both the evaluator (which compares ids)
    and the serializer (which emits a URL built from the path) work without the
    bytes existing. Writing real PNGs would make these tests slower and would
    test Pillow.
    """
    question = SingleAnswerImageQuestion.objects.create(**_base(slug, level, category))
    for order, (name, is_correct) in enumerate(options, start=1):
        ImageAnswerOption.objects.create(
            question=question,
            image=f"questions/answers/nba/{name}",
            label=name.split(".")[0],
            is_correct=is_correct,
            order=order,
        )
    return question


def make_multiple_answer(
    *,
    slug: str = "several",
    level: int = 5,
    category: Category | None = None,
    options: tuple[tuple[str, bool], ...] = (
        ("Bill Russell", True),
        ("Kareem Abdul-Jabbar", True),
        ("Karl Malone", False),
        ("Charles Barkley", False),
    ),
) -> MultipleAnswerQuestion:
    question = MultipleAnswerQuestion.objects.create(**_base(slug, level, category))
    for order, (text, is_correct) in enumerate(options, start=1):
        MultipleAnswerOption.objects.create(
            question=question, text=text, is_correct=is_correct, order=order
        )
    return question


def make_true_false(
    *,
    slug: str = "claim",
    level: int = 1,
    category: Category | None = None,
    answer: bool = True,
) -> TrueFalseQuestion:
    return TrueFalseQuestion.objects.create(**_base(slug, level, category), answer=answer)


def make_free_text(
    *,
    slug: str = "typed",
    level: int = 4,
    category: Category | None = None,
    accepted: tuple[str, ...] = ("Kobe Bryant", "Kobe"),
) -> FreeTextQuestion:
    question = FreeTextQuestion.objects.create(**_base(slug, level, category))
    for value in accepted:
        FreeTextAnswer.objects.create(question=question, value=value)
    return question


def make_ordering(
    *,
    slug: str = "sorted",
    level: int = 6,
    category: Category | None = None,
    items: tuple[str, ...] = ("1991", "1992", "1993", "1996"),
) -> OrderingQuestion:
    """``items`` is authored in its **correct** order, as the resource files are —
    the list order is the answer, so positions cannot have a gap."""
    question = OrderingQuestion.objects.create(
        **_base(slug, level, category), instruction="Earliest first."
    )
    for position, text in enumerate(items, start=1):
        OrderingOption.objects.create(
            question=question, text=text, correct_position=position
        )
    return question


def make_gradual_hints(
    *,
    slug: str = "hinted",
    level: int = 6,
    category: Category | None = None,
    hints: tuple[str, ...] = (
        "The final score was 93-89",
        "Draymond Green hit six threes",
        "OH, BLOCKED BY JAMES!",
    ),
    hint_interval_seconds: int = 5,
    answer_fields: tuple[tuple[str, tuple[str, ...], str], ...] = (
        ("Year", ("2016",), AnswerFieldKind.NUMBER),
        ("Round", ("Finals", "NBA Finals"), AnswerFieldKind.TEXT),
        ("Game number", ("7", "Game 7"), AnswerFieldKind.TEXT),
    ),
) -> GradualHintsQuestion:
    """Three clues and three boxes — deliberately more than one of each.

    Several fields is what makes the per-field denominator testable at all (one
    box would make every answer all-or-nothing by arithmetic rather than by
    rule), and one of the three accepts two spellings, so "any accepted answer
    fills the field" is exercised by every suite that builds one without asking
    for it. Both field kinds are here for the same reason — a board that sized
    every box the same would pass a fixture that only ever built one kind. ``hints`` is authored hardest-first, as a resource file is: the list
    order is the reveal order.
    """
    question = GradualHintsQuestion.objects.create(
        **_base(slug, level, category), hint_interval_seconds=hint_interval_seconds
    )
    for order, text in enumerate(hints, start=1):
        GradualHint.objects.create(question=question, order=order, text=text)
    for order, (label, accepted, kind) in enumerate(answer_fields, start=1):
        field = GradualHintsField.objects.create(
            question=question, order=order, label=label, kind=kind
        )
        for value in accepted:
            GradualHintsFieldAnswer.objects.create(field=field, value=value)
    return question


#: What a factory caller may write for one cell's answers: a single value,
#: or several — each of them either a string or ``(value, probability_score)``.
CellAnswers = Union[str, tuple[str, int], Sequence[Union[str, tuple[str, int]]]]


def _cell_answers(answers: CellAnswers) -> list[tuple[str, int]]:
    """Normalise a factory caller's shorthand into ``(value, score)`` pairs."""
    if isinstance(answers, str):
        answers = [answers]
    elif isinstance(answers, tuple) and len(answers) == 2 and isinstance(answers[1], int):
        answers = [answers]
    return [
        (answer, DEFAULT_PROBABILITY_SCORE) if isinstance(answer, str) else answer
        for answer in answers
    ]


def make_matrix(
    *,
    slug: str = "grid",
    level: int = 7,
    category: Category | None = None,
    rows: tuple[str, ...] = ("Bulls", "Lakers"),
    columns: tuple[str, ...] = ("1990s", "2000s"),
    cells: tuple[tuple[str, str, CellAnswers], ...] = (
        ("Bulls", "1990s", "1996"),
        ("Lakers", "2000s", ("2001", "2002")),
        ("Lakers", "1990s", "1988"),
    ),
) -> ColumnsRowsQuestion:
    """Sparse by default: three of the four intersections are authored.

    Deliberate — the fourth cell is what makes it possible to test that a player
    answering an intersection nobody asked about is refused, and that the
    per-cell denominator is the authored cells rather than rows x columns.

    A cell's answer is either one string or several: one of the three defaults
    accepts two, so the "any accepted answer takes the cell" rule is exercised
    by every suite that builds a grid without asking for it. Each answer can
    also be written ``(value, probability_score)`` where a test cares about the
    grade.
    """
    question = ColumnsRowsQuestion.objects.create(
        **_base(slug, level, category),
        row_count=len(rows),
        column_count=len(columns),
    )
    row_rows = {
        title: MatrixRow.objects.create(question=question, title=title, order=order)
        for order, title in enumerate(rows, start=1)
    }
    column_rows = {
        title: MatrixColumn.objects.create(question=question, title=title, order=order)
        for order, title in enumerate(columns, start=1)
    }
    for row, column, answers in cells:
        cell = MatrixCell.objects.create(
            question=question,
            row=row_rows[row],
            column=column_rows[column],
        )
        for value, probability_score in _cell_answers(answers):
            MatrixCellAnswer.objects.create(
                cell=cell, value=value, probability_score=probability_score
            )
    return question


def make_team_matrix(
    *,
    slug: str = "team-grid",
    level: int = 7,
    category: Category | None = None,
    rows: tuple[str, ...] = ("Chicago Bulls", "Los Angeles Lakers"),
    columns: tuple[str, ...] = ("Washington Wizards", "Miami Heat"),
    cells: tuple[tuple[str, str], ...] | None = None,
) -> ColumnsRowsQuestion:
    """A ``kind: teams`` grid — cells with no answers, on purpose.

    The mirror of :func:`make_matrix`, and the *only* difference that matters is
    what is missing: no ``MatrixCellAnswer`` rows, because a team grid's answer
    key is ``apps.questions.rosters`` and a test that seeded answers here would
    be testing the authored path under a different name.

    ``cells`` defaults to every intersection of two different franchises, which
    is what the loader derives for headings this well-populated. Pass it to
    build a sparser grid — a pairing left out is a pairing the evaluator must
    refuse.
    """
    question = ColumnsRowsQuestion.objects.create(
        **_base(slug, level, category),
        row_count=len(rows),
        column_count=len(columns),
        kind=MatrixKind.TEAMS,
    )
    row_rows = {
        title: MatrixRow.objects.create(question=question, title=title, order=order)
        for order, title in enumerate(rows, start=1)
    }
    column_rows = {
        title: MatrixColumn.objects.create(question=question, title=title, order=order)
        for order, title in enumerate(columns, start=1)
    }
    if cells is None:
        cells = tuple(
            (row, column)
            for row in rows
            for column in columns
            if row != column
        )
    for row, column in cells:
        MatrixCell.objects.create(
            question=question,
            row=row_rows[row],
            column=column_rows[column],
        )
    return question


def make_name_as_many(
    *,
    slug: str = "name-as-many",
    level: int = 5,
    category: Category | None = None,
    stat: str = "fg3m",
    comparison: str = StatComparison.AT_LEAST,
    threshold: float = 1000,
    target_score: int = 10,
) -> NameAsManyQuestion:
    """A question with no children at all — the line *is* the question.

    The defaults are the real artifact's: ``fg3m`` at 1,000, which is what
    ``resources/nba/name-as-many.yaml`` asks and what the test fixtures in
    ``test_career_stats`` are cut against. A suite wanting a question the
    artifact cannot answer passes a stat nobody baked; nothing here validates
    it, because validating it is the *loader's* job and a factory that enforced
    load-time rules would make every evaluator test a loader test.
    """
    return NameAsManyQuestion.objects.create(
        **_base(slug, level, category),
        stat=stat,
        comparison=comparison,
        threshold=threshold,
        target_score=target_score,
    )


#: One builder per question type, keyed by the type's YAML key — so a suite can
#: walk every shape without naming them, and a new question type joins those
#: suites by adding a line here.
QUESTION_FACTORIES = {
    QuestionType.SINGLE_ANSWER: make_single_answer,
    QuestionType.IMAGE_ANSWER: make_image_answer,
    QuestionType.MULTIPLE_ANSWER: make_multiple_answer,
    QuestionType.TRUE_FALSE: make_true_false,
    QuestionType.FREE_TEXT: make_free_text,
    QuestionType.ORDERING: make_ordering,
    QuestionType.MATRIX: make_matrix,
    QuestionType.GRADUAL_HINTS: make_gradual_hints,
    QuestionType.NAME_AS_MANY: make_name_as_many,
}
