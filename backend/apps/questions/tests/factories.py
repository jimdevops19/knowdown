"""Question rows, built directly.

The loader has its own suite (``test_sync``); everything else wants *a question
of this shape* in as few lines as possible, and going through YAML to get one
would make every evaluator test a loader test too — so a break in the loader
would fail all of them and say nothing about which.

Every builder takes the same knobs (``slug``, ``level``, ``category``) and
returns a saved question with its children, numbered the way the loader numbers
them: options in list order, ordering positions 1..n. That similarity is what
lets the evaluator and serializer suites be table-driven over
``QUESTION_MODELS`` instead of naming seven shapes twice each.
"""

from __future__ import annotations

from apps.categories.models import Category
from apps.questions.models import (
    ColumnsRowsQuestion,
    FreeTextAnswer,
    FreeTextQuestion,
    ImageAnswerOption,
    MatrixCell,
    MatrixColumn,
    MatrixRow,
    MultipleAnswerOption,
    MultipleAnswerQuestion,
    OrderingOption,
    OrderingQuestion,
    QuestionType,
    SingleAnswerImageQuestion,
    SingleAnswerOption,
    SingleAnswerQuestion,
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


def make_matrix(
    *,
    slug: str = "grid",
    level: int = 7,
    category: Category | None = None,
    rows: tuple[str, ...] = ("Bulls", "Lakers"),
    columns: tuple[str, ...] = ("1990s", "2000s"),
    cells: tuple[tuple[str, str, str], ...] = (
        ("Bulls", "1990s", "1996"),
        ("Lakers", "2000s", "2001"),
        ("Lakers", "1990s", "1988"),
    ),
) -> ColumnsRowsQuestion:
    """Sparse by default: three of the four intersections are authored.

    Deliberate — the fourth cell is what makes it possible to test that a player
    answering an intersection nobody asked about is refused, and that the
    per-cell denominator is the authored cells rather than rows x columns.
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
    for row, column, answer in cells:
        MatrixCell.objects.create(
            question=question,
            row=row_rows[row],
            column=column_rows[column],
            answer=answer,
        )
    return question


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
}
