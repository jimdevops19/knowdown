"""Abstract base models shared by every domain app.

Compose these rather than inheriting ``models.Model`` directly so that UUID
primary keys, timestamps and soft delete are uniform across the platform::

    class Category(BaseModel):
        name = models.CharField(max_length=100)

``BaseModel`` = UUID pk + created/updated timestamps + soft delete.
"""

from __future__ import annotations

import uuid

from django.db import IntegrityError, models, router, transaction
from django.utils.text import slugify

from .deletion import SoftDeleteCollector
from .managers import AllObjectsManager, SoftDeleteManager


class UUIDPrimaryKeyModel(models.Model):
    """Opaque, non-sequential UUID primary key (safe to expose in URLs)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Adds ``deleted_at`` and rewires ``delete()`` to soft-delete."""

    deleted_at = models.DateTimeField(
        null=True, blank=True, editable=False, db_index=True
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def delete(self, using=None, keep_parents=False):  # type: ignore[override]
        """Soft delete, cascading exactly the way a hard delete would: walks
        every FK pointing at this row via the same ``Collector`` Django's own
        ``Model.delete()`` uses (see ``core_common.deletion``), so CASCADE/
        PROTECT/SET_NULL behave identically — the only difference is that
        collected rows are stamped ``deleted_at`` instead of removed."""
        using = using or router.db_for_write(self.__class__, instance=self)
        collector = SoftDeleteCollector(using=using, origin=self)
        collector.collect([self], keep_parents=keep_parents)
        collector.delete()

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self) -> None:
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])


class BaseModel(UUIDPrimaryKeyModel, TimeStampedModel, SoftDeleteModel):
    """The default base for domain models."""

    class Meta:
        abstract = True
        ordering = ("-created_at",)


class SluggedModel:
    """Fills a blank ``slug`` from another field, and guarantees it is free.

    Slugs here are *keys*: a category is looked up by one in the API, and a
    question's slug is what its YAML entry is authored under and what
    ``sync_questions`` upserts on. That makes uniqueness the model's problem
    rather than the caller's, for the rows that are created in the admin or from
    a fixture rather than from a resource file.

    A second row whose name slugifies the same becomes ``nba-2``. Collisions are
    resolved by counting, not by a random token, because these end up in URLs
    and in the resource files people read.

    Uniqueness is checked against ``all_objects``: a soft-deleted row still
    occupies its slug in the database's unique index, so skipping it here would
    just move the IntegrityError to the INSERT.

    Concurrency is handled by *retrying* rather than by locking. Probing for a
    free slug and then inserting can never be atomic on its own — two processes
    can both see ``nba-2`` free — so each attempt runs inside a savepoint and a
    lost race simply picks the next number. This is why the class must sit to the
    LEFT of the model base (``class Category(SluggedModel, BaseModel)``): it
    works by wrapping ``save()``.
    """

    slug_source = "name"
    #: Candidates tried before giving up. Reached only if that many rows really
    #: do share a name, which is not a case worth a longer scan.
    slug_attempts = 50

    def _slug_max_length(self) -> int:
        return self._meta.get_field("slug").max_length

    def _slug_base(self) -> str:
        base = slugify(getattr(self, self.slug_source, "") or "")
        # slugify strips everything non-alphanumeric, so a name that is entirely
        # emoji or CJK punctuation comes back empty — and an empty slug is not a
        # usable key and collides with every other such name.
        return base or self._meta.model_name

    def _slug_candidates(self):
        limit = self._slug_max_length()
        base = self._slug_base()[:limit]
        yield base

        manager = getattr(type(self), "all_objects", None) or type(self)._default_manager
        taken = set(
            manager.filter(
                models.Q(slug=base) | models.Q(slug__startswith=f"{base}-")
            ).values_list("slug", flat=True)
        )
        for n in range(2, self.slug_attempts + 2):
            suffix = f"-{n}"
            candidate = f"{base[: limit - len(suffix)]}{suffix}"
            if candidate not in taken:
                yield candidate

    def save(self, *args, **kwargs):
        if self.slug:
            return super().save(*args, **kwargs)

        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        last: IntegrityError | None = None
        for candidate in self._slug_candidates():
            self.slug = candidate
            try:
                with transaction.atomic(using=using):
                    return super().save(*args, **kwargs)
            except IntegrityError as exc:
                if "slug" not in str(exc):
                    raise  # some other constraint — not ours to retry
                last = exc
        self.slug = ""
        raise last  # type: ignore[misc]
