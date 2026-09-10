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

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, QuerySet

from apps.categories.models import Category
from apps.core_common.exceptions import NotFound, ValidationFailed
from apps.questions.constants import (
    LEVEL_BANDS,
    LONGEST_MATCH_QUESTION_COUNT,
    LevelBand,
)
from apps.questions.models import QUESTION_MODELS, MAX_LEVEL, BaseQuestion

__all__ = [
    "BandDepth",
    "CategoryDepth",
    "QuestionRef",
    "available_questions",
    "catalog_depth",
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

    Containment is expressed as one key-path lookup per facet
    (``tags__era="2000s"``) rather than as ``tags__contains={...}``. They mean
    the same thing for the flat string dict ``tags`` holds, and only one of them
    works everywhere: ``contains`` on a ``JSONField`` is unsupported on SQLite,
    which is the zero-config local backend — so the other spelling turns a
    themed round into a crash on every machine without PostgreSQL, and passes
    the suite, which runs on SQLite too.
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
        # A key-path lookup addresses a *key*, and a digit would address an array
        # index instead — so a facet named "2000s" would silently match nothing.
        # Refused rather than filtered, because a themed round quietly returning
        # an untagged pool is worse than one that will not start.
        if not key.replace("_", "").replace("-", "").isalpha():
            raise ValidationFailed(
                f"Tag key {key!r} must be alphabetic (with - or _), because a "
                f"key path containing a digit addresses an array index."
            )
        queryset = queryset.filter(**{f"tags__{key}": value})

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
    except (
        model.DoesNotExist,
        ValueError,
        ValidationFailed,
        # A ``UUIDField`` refuses an id that is not a UUID at all before it ever
        # reaches the database, and it does so with Django's own
        # ``ValidationError`` — which is not a ``ValueError``. Caught here
        # because an id nobody could have issued is a question that does not
        # exist, not a malformed request: a ref is built from stored data
        # (``MatchupQuestion``) or from a URL, and both answer 404.
        DjangoValidationError,
    ) as exc:
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


# --- How deep the catalog is ------------------------------------------------
#
# A thin category is not a shorter match, it is a broken one (see
# `select_questions`), which makes "is there enough to play?" a question worth
# being able to ask *before* two players are waiting on the answer. That is what
# `manage.py questions_report` prints, and these are the reads behind it.


@dataclass(frozen=True)
class BandDepth:
    """How many askable questions one category holds in one level band."""

    band: LevelBand
    #: Per question type, so a band that is deep overall but has, say, no
    #: ordering questions is visible rather than averaged away.
    by_type: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.by_type.values())

    def playable(self, *, count: int = LONGEST_MATCH_QUESTION_COUNT) -> bool:
        """Whether a match of ``count`` questions can be drawn from this band.

        The same comparison ``select_questions`` makes, asked ahead of time
        instead of at the moment two players are paired.
        """
        return self.total >= count


@dataclass(frozen=True)
class CategoryDepth:
    """One category, band by band."""

    category: Category
    bands: tuple[BandDepth, ...]

    @property
    def total(self) -> int:
        return sum(band.total for band in self.bands)

    @property
    def by_type(self) -> dict[str, int]:
        totals = {question_type: 0 for question_type in QUESTION_MODELS}
        for band in self.bands:
            for question_type, count in band.by_type.items():
                totals[question_type] += count
        return totals

    def thin_bands(
        self, *, count: int = LONGEST_MATCH_QUESTION_COUNT
    ) -> list[BandDepth]:
        """The bands that cannot fill a match — the reason the report exits
        non-zero."""
        return [band for band in self.bands if not band.playable(count=count)]


def _counts_by_level(*, model: type[BaseQuestion], category: Category) -> dict[int, int]:
    """How many askable questions of one type sit at each level.

    One grouped query per type rather than one count per (type, band): the
    report asks about every band at once, and 3 bands x 7 types x N categories
    of `COUNT(*)` is a lot of round trips to print a small table.

    ``order_by()`` is not decoration — ``BaseQuestion.Meta.ordering`` is
    ``("slug",)``, and a default ordering silently joins the GROUP BY, which
    would return one row per question rather than one per level.
    """
    return dict(
        available_questions(model=model, category=category)
        .order_by()
        .values("level")
        .annotate(count=Count("id"))
        .values_list("level", "count")
    )


def catalog_depth(*, categories: list[Category] | None = None) -> list[CategoryDepth]:
    """The catalog, counted per category, per band, per type.

    Only *active* categories by default, and (through ``available_questions``)
    only active questions — the report answers "what can be played right now",
    which is the number that matters when a match refuses to start. A
    deactivated category holding a thin band is not a problem to fix.
    """
    if categories is None:
        categories = list(Category.objects.filter(is_active=True))

    depths: list[CategoryDepth] = []
    for category in categories:
        per_type_by_level = {
            question_type: _counts_by_level(model=model, category=category)
            for question_type, model in QUESTION_MODELS.items()
        }
        depths.append(
            CategoryDepth(
                category=category,
                bands=tuple(
                    BandDepth(
                        band=band,
                        by_type={
                            question_type: sum(
                                count
                                for level, count in by_level.items()
                                if band.contains(level)
                            )
                            for question_type, by_level in per_type_by_level.items()
                        },
                    )
                    for band in LEVEL_BANDS
                ),
            )
        )
    return depths
