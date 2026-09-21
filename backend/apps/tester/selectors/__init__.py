"""Finding the question you came here to debug.

The read side of the tester, and the reason it is not
``apps.questions.selectors``: that module answers "what may be *played*" — it
filters to active questions and active categories because that is what the word
means to a match (``available_questions``). A maintainer is looking for the
question that is broken, and a question that is broken is quite often a question
somebody has just deactivated. Bolting an ``include_inactive`` switch onto the
selection seam the match engine calls would put a way to serve a retired
question one keyword argument from the live path, which is the trade this file
exists to refuse.

**One query per table, then sorted in Python.** A question is eight tables
(``models.QUESTION_MODELS``), so a catalog listing cannot be one queryset and no
amount of wanting it to be will make it one. Eight indexed queries returning a
page's worth of rows each is a fine price for a page only maintainers open, and
the alternative — a ``UNION`` over tables with different columns — buys database
ordering at the cost of losing the model instances the serializer needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.db.models import Q

from apps.categories.models import Category
from apps.questions.constants import LEVEL_BANDS
from apps.questions.models import QUESTION_MODELS, BaseQuestion

__all__ = [
    "CatalogCounts",
    "catalog_counts",
    "search_questions",
]


def search_questions(
    *,
    search: str | None = None,
    category_slug: str | None = None,
    question_type: str | None = None,
    level_range: tuple[int, int] | None = None,
    include_inactive: bool = True,
    created_after: datetime | None = None,
) -> list[BaseQuestion]:
    """Every question matching the filters, across every answer shape.

    ``include_inactive`` defaults to **True**, the opposite of everything in
    ``apps.questions.selectors``, and that is the point of the module docstring
    above: the default here is "show me what is in the database", because that
    is the question a maintainer is asking. The caller narrows it.

    ``search`` matches the slug, the question text, or the category name —
    case-insensitively, as one ``icontains`` each. Not full-text search: the
    catalog is thousands of rows, not millions, and a maintainer typing "kobe"
    wants the same three questions either way.

    ``created_after`` is what turns "review what I just synced" into a filter:
    ``created_at`` is already on every question via ``BaseModel``
    (``auto_now_add``, indexed), so this is a plain ``gte`` on a column that was
    always there — nothing to add to any question, just a way to ask for it.
    """
    filters = Q()
    if category_slug:
        filters &= Q(category__slug=category_slug)
    if level_range is not None:
        low, high = level_range
        filters &= Q(level__gte=low, level__lte=high)
    if not include_inactive:
        filters &= Q(is_active=True)
    if created_after is not None:
        filters &= Q(created_at__gte=created_after)
    if search:
        term = search.strip()
        if term:
            filters &= (
                Q(slug__icontains=term)
                | Q(description__icontains=term)
                | Q(category__name__icontains=term)
            )

    wanted = (
        {question_type: QUESTION_MODELS[question_type]}
        if question_type in QUESTION_MODELS
        else QUESTION_MODELS
    )

    found: list[BaseQuestion] = []
    for model in wanted.values():
        # `select_related` because every card names its category, and eight
        # queries turning into eight-plus-a-page-of-rows is the N+1 this page
        # would otherwise notice first.
        found.extend(model.objects.select_related("category").filter(filters))

    # Sorted the way the list is read rather than the way it was fetched: a
    # maintainer scanning for a question thinks "NBA, the easy ones", not "all
    # the true/false ones first". Slug last, so the order is total and a
    # paginated list cannot show the same row on two pages.
    #
    # Except when reviewing a fresh batch (`created_after` set): there, newest
    # first is the order that matters — the whole point is skimming the rows a
    # sync just wrote, not re-deriving which ones those were from a category
    # sort.
    if created_after is not None:
        found.sort(key=lambda q: q.created_at, reverse=True)
    else:
        found.sort(key=lambda q: (q.category.name, q.level, q.slug))
    return found


@dataclass(frozen=True)
class CatalogCounts:
    """How much there is to look at, split the three ways the page filters it.

    All three are counts of the *whole* catalog, active or not — the filter bar is
    built from this, and a type whose only questions are deactivated still needs
    its entry there or there is no way to go and look at them.
    """

    #: ``{category slug: (name, count)}``, only categories that hold something.
    categories: dict[str, tuple[str, int]]
    #: ``{question type: count}`` — every type, including the ones at zero, so
    #: an empty type reads as "none authored yet" rather than as a missing row.
    types: dict[str, int]
    #: ``{band name: count}`` over ``questions.constants.LEVEL_BANDS`` — every
    #: band, including the empty ones, for the same reason every type is here.
    levels: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.types.values())


def catalog_counts() -> CatalogCounts:
    """The filter bar's vocabulary: a count per table, per category and per band.

    Counting rather than grouping, over eight tables and a handful of buckets,
    because a ``COUNT(*)`` with an indexed ``WHERE`` is cheap and this is asked
    once when a maintainer opens the page — the same trade ``search_questions``
    makes above.
    """
    types = {
        question_type: model.objects.count()
        for question_type, model in QUESTION_MODELS.items()
    }

    per_category: dict[str, tuple[str, int]] = {}
    for category in Category.objects.all():
        count = sum(
            model.objects.filter(category=category).count()
            for model in QUESTION_MODELS.values()
        )
        if count:
            per_category[category.slug] = (category.name, count)

    levels = {
        band.name: sum(
            model.objects.filter(level__gte=band.low, level__lte=band.high).count()
            for model in QUESTION_MODELS.values()
        )
        for band in LEVEL_BANDS
    }

    return CatalogCounts(categories=per_category, types=types, levels=levels)
