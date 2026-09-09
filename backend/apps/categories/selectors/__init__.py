"""The read side of categories."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.categories.models import Category
from apps.core_common.exceptions import NotFound

__all__ = ["active_categories", "get_category_by_slug"]


def active_categories() -> QuerySet[Category]:
    """Every category questions may currently be drawn from.

    ``active`` is what "a category" *means* to anything outside the admin, so
    the filter lives here rather than in each view — no caller can offer a
    half-authored sport by forgetting it.
    """
    return Category.objects.filter(is_active=True)


def get_category_by_slug(*, slug: str, include_inactive: bool = False) -> Category:
    """One category, by the name everything else calls it.

    ``include_inactive`` is for the loader, which has to find a category it is
    about to write to whatever state it is in.
    """
    queryset = Category.objects.all() if include_inactive else active_categories()
    try:
        return queryset.get(slug=slug)
    except Category.DoesNotExist as exc:
        raise NotFound(f"No category with slug '{slug}'.") from exc
