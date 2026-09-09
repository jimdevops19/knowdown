"""Reusable managers and querysets.

Soft delete is implemented here once and mixed into every domain model via
``SoftDeleteModel``. The default manager hides soft-deleted rows; ``all_objects``
exposes them for admin/audit use.
"""

from __future__ import annotations

from django.db import models

from .deletion import SoftDeleteCollector


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):  # type: ignore[override]
        """Soft delete, cascading through related models' ``on_delete`` the
        same way an instance ``.delete()`` does (see ``SoftDeleteCollector``)
        — a bulk queryset delete must behave identically to deleting each row
        one at a time, not silently skip the cascade."""
        self._not_support_combined_queries("delete")
        del_query = self._chain()
        del_query._for_write = True
        del_query.query.select_for_update = False
        del_query.query.select_related = False
        del_query.query.clear_ordering(force=True)

        collector = SoftDeleteCollector(using=del_query.db, origin=self)
        collector.collect(del_query)
        deleted, _rows_count = collector.delete()

        self._result_cache = None
        return deleted, _rows_count

    def hard_delete(self):
        return super().delete()

    def alive(self) -> "SoftDeleteQuerySet":
        return self.filter(deleted_at__isnull=True)

    def dead(self) -> "SoftDeleteQuerySet":
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager):
    """Default manager: only rows that have not been soft-deleted."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class AllObjectsManager(models.Manager):
    """Escape hatch: includes soft-deleted rows."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        return SoftDeleteQuerySet(self.model, using=self._db)
