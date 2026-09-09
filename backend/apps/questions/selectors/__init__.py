"""The read side of questions — including how a matchup's questions are drawn.

Selection lives in this app rather than in ``apps.matches`` deliberately: the
match engine must stay independent of the concrete question type, so "give me
five NBA questions" is a question the questions domain answers and the match
domain merely asks. What comes back is a list of :class:`QuestionRef` — a
``(type, id)`` pair — which is exactly what ``matches.MatchupQuestion`` will
store, and it is the reason the match tables need no foreign key into seven
different question tables.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from django.db.models import QuerySet

from apps.categories.models import Category
from apps.core_common.exceptions import NotFound, ValidationFailed
from apps.questions.models import QUESTION_MODELS, MAX_LEVEL, BaseQuestion

__all__ = [
    "QuestionRef",
    "available_questions",
    "get_question",
    "question_by_slug",
    "question_pool",
    "select_questions",
]


@dataclass(frozen=True)
class QuestionRef:
    """Which table, and which row in it.

    A question is not one model (see ``apps.questions.models``), so nothing can
    hold "a question" in a single foreign key. This pair is what stands in for
    one everywhere the type is not known ahead of time.
    """

    question_type: str
    question_id: str

    def as_tuple(self) -> tuple[str, str]:
        return self.question_type, self.question_id


def available_questions(
    *,
    model: type[BaseQuestion],
    category: Category,
    level_range: tuple[int, int] | None = None,
    tags: dict[str, str] | None = None,
) -> QuerySet:
    """Everything of one type that may be asked in this category right now.

    ``is_active`` is what "available" *means*, so the filter lives here and no
    caller can serve a retired question by forgetting it.

    ``tags`` matches on containment — an entry with extra facets still matches a
    narrower filter — because tags are how a themed round ("2000s finals") gets
    built out of the same catalog.
    """
    queryset = model.objects.filter(category=category, is_active=True)

    if level_range:
        low, high = level_range
        if not 1 <= low <= high <= MAX_LEVEL:
            raise ValidationFailed(
                f"level_range must be within 1..{MAX_LEVEL} and ascending, got "
                f"{level_range}."
            )
        queryset = queryset.filter(level__gte=low, level__lte=high)

    for key, value in (tags or {}).items():
        queryset = queryset.filter(tags__contains={key: value})

    return queryset


def question_pool(
    *,
    category: Category,
    level_range: tuple[int, int] | None = None,
    tags: dict[str, str] | None = None,
    types: list[str] | None = None,
) -> list[QuestionRef]:
    """Every askable question in a category, across every answer shape.

    One query per type rather than a union: the tables have different columns, and
    only the ids are wanted here anyway. ``types`` narrows it — a round of nothing
    but true/false is a legitimate thing to want, and it is also how a new question
    type is rolled out to part of the audience.
    """
    wanted = types or list(QUESTION_MODELS)
    unknown = set(wanted) - set(QUESTION_MODELS)
    if unknown:
        raise ValidationFailed(f"Unknown question type(s): {', '.join(sorted(unknown))}.")

    pool: list[QuestionRef] = []
    for question_type in wanted:
        ids = available_questions(
            model=QUESTION_MODELS[question_type],
            category=category,
            level_range=level_range,
            tags=tags,
        ).values_list("id", flat=True)
        pool.extend(QuestionRef(question_type, str(pk)) for pk in ids)
    return pool


def select_questions(
    *,
    category: Category,
    count: int,
    level_range: tuple[int, int] | None = None,
    tags: dict[str, str] | None = None,
    types: list[str] | None = None,
    rng: random.Random | None = None,
) -> list[QuestionRef]:
    """Draw ``count`` distinct questions for one matchup.

    The **server** chooses, and it chooses once for both players — the same
    questions in the same order, so a match is a race and not two different
    quizzes. Refusing when the pool is too small is deliberate: silently playing
    a shorter match would make the number of questions depend on how well stocked
    a category happens to be, which is a rule nobody agreed to.

    ``rng`` is injectable so a test can pin the draw; production passes nothing
    and gets ``random``'s own.
    """
    if count < 1:
        raise ValidationFailed("A matchup needs at least one question.")

    pool = question_pool(
        category=category, level_range=level_range, tags=tags, types=types
    )
    if len(pool) < count:
        raise ValidationFailed(
            f"Category '{category.slug}' has {len(pool)} askable questions, "
            f"{count} were requested.",
            code="not_enough_questions",
        )
    return (rng or random).sample(pool, count)


def get_question(*, ref: QuestionRef) -> BaseQuestion:
    """The row a :class:`QuestionRef` points at.

    Answers with the question whether or not it is still active: a matchup being
    replayed or reviewed asks for exactly the question that was played, and a
    question retired since then is still what happened.
    """
    model = QUESTION_MODELS.get(ref.question_type)
    if model is None:
        raise NotFound(f"Unknown question type '{ref.question_type}'.")
    try:
        return model.objects.get(id=ref.question_id)
    except (model.DoesNotExist, ValueError, ValidationFailed) as exc:
        raise NotFound(f"No {ref.question_type} question with id {ref.question_id}.") from exc


def question_by_slug(*, slug: str) -> BaseQuestion:
    """One question by the name its YAML entry is authored under.

    Walks the registry because a slug does not say which table it lives in — the
    price of one table per answer shape, paid once, here.
    """
    for model in QUESTION_MODELS.values():
        question = model.objects.filter(slug=slug).first()
        if question is not None:
            return question
    raise NotFound(f"No question with slug '{slug}'.")
