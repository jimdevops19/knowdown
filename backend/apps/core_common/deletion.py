"""Cascading *soft* delete.

Every FK on a domain model already declares what should happen when the row it
points to disappears — ``on_delete=CASCADE``, ``PROTECT``, ``SET_NULL``, etc.
Django's default ``Model.delete()`` reads those declarations via
``django.db.models.deletion.Collector``, which walks the whole related-object
graph and applies them. A soft delete that merely stamped ``deleted_at`` on the
single row it was called on would skip all of that — a question's options would
be silently left behind, and every declared ``PROTECT``/``SET_NULL`` would be
dead weight on any soft-deleted model.

``SoftDeleteCollector`` reuses ``Collector.collect()`` completely unchanged —
that is the part that walks the graph and enforces PROTECT/RESTRICT — and only
overrides the final ``delete()`` step: instead of issuing SQL DELETEs it stamps
``deleted_at`` on every collected row that supports soft delete, falling back to
a real delete for rows that do not. This is what makes deleting a question
cascade to its options, rows, columns and cells without a hand-written service
enumerating each one, while the category it belongs to stays untouched because
nothing about deleting a question points *at* a category for deletion.
"""

from __future__ import annotations

from collections import Counter
from functools import reduce
from operator import attrgetter, or_

from django.db import models, transaction
from django.db.models import signals, sql
from django.db.models.deletion import Collector
from django.utils import timezone


def _supports_soft_delete(model) -> bool:
    return hasattr(model, "deleted_at")


class SoftDeleteCollector(Collector):
    """A :class:`~django.db.models.deletion.Collector` whose ``delete()``
    soft-deletes collected rows instead of removing them. Collection —
    graph-walking, CASCADE recursion, PROTECT/RESTRICT enforcement,
    SET_NULL/SET_DEFAULT field updates — is inherited unchanged."""

    def delete(self):
        for model, instances in self.data.items():
            self.data[model] = sorted(instances, key=attrgetter("pk"))
        self.sort()
        deleted_counter = Counter()
        now = timezone.now()

        with transaction.atomic(using=self.using, savepoint=False):
            for model, obj in self.instances_with_model():
                if not model._meta.auto_created:
                    signals.pre_delete.send(
                        sender=model, instance=obj, using=self.using, origin=self.origin,
                    )

            # Fast deletes: leaf batches with nothing further to cascade to.
            # Route through soft delete too, when the model supports it.
            for qs in self.fast_deletes:
                if _supports_soft_delete(qs.model):
                    count = qs.update(deleted_at=now)
                else:
                    count = qs._raw_delete(using=self.using)
                if count:
                    deleted_counter[qs.model._meta.label] += count

            # SET_NULL / SET_DEFAULT / SET(...) field updates — identical to
            # the base Collector; nulling/defaulting a field is the same
            # operation regardless of how the row that triggered it is removed.
            for (field, value), instances_list in self.field_updates.items():
                updates = []
                objs = []
                for instances in instances_list:
                    if (
                        isinstance(instances, models.QuerySet)
                        and instances._result_cache is None
                    ):
                        updates.append(instances)
                    else:
                        objs.extend(instances)
                if updates:
                    combined_updates = reduce(or_, updates)
                    combined_updates.update(**{field.name: value})
                if objs:
                    upd_model = objs[0].__class__
                    query = sql.UpdateQuery(upd_model)
                    query.update_batch(
                        list({obj.pk for obj in objs}), {field.name: value}, self.using
                    )

            for instances in self.data.values():
                instances.reverse()

            for model, instances in self.data.items():
                pk_list = [obj.pk for obj in instances]
                if _supports_soft_delete(model):
                    count = model._base_manager.filter(pk__in=pk_list).update(
                        deleted_at=now
                    )
                    for obj in instances:
                        obj.deleted_at = now
                else:
                    query = sql.DeleteQuery(model)
                    count = query.delete_batch(pk_list, self.using)
                    for obj in instances:
                        setattr(obj, model._meta.pk.attname, None)
                if count:
                    deleted_counter[model._meta.label] += count

                if not model._meta.auto_created:
                    for obj in instances:
                        signals.post_delete.send(
                            sender=model, instance=obj, using=self.using, origin=self.origin,
                        )

        return sum(deleted_counter.values()), dict(deleted_counter)
