"""Loading ``resources/rooms.yaml`` into the ``Room`` tables.

The same authoring loop as ``apps.questions.services.sync`` and
``apps.achievements.services.sync``, and deliberately the same four rules, so
that "how do I change a thing on this platform?" has one answer:

- **Upserted on ``slug``**, so renaming a room or adding a category to it
  re-runs into the same row rather than beside it.
- **Nothing is deleted.** A room dropped from the file is deactivated — a
  matchup already played in it points at that row, and a hard delete would edit
  a game two people have finished.
- **Everything is validated before anything is written**, including the
  categories every room points at, so a typo in the last room does not leave
  the first three loaded.
- **Child rows are replaced, not diffed.** A room's categories carry no history
  of their own (a played matchup records the room, and its board records the
  questions that were actually drawn), and matching them across a reload would
  need a key nobody wants to author.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from django.db import transaction

from apps.categories.models import Category
from apps.core_common.exceptions import ValidationFailed
from apps.rooms.models import Room, RoomCategory
from apps.rooms.schemas import RoomSpec
from shared.logging import get_logger

logger = get_logger(__name__)

__all__ = ["LoadReport", "ROOMS_FILE", "sync_rooms"]

#: apps/rooms/services/sync.py -> apps/rooms/resources
RESOURCES = Path(__file__).resolve().parent.parent / "resources"
ROOMS_FILE = RESOURCES / "rooms.yaml"


@dataclass
class LoadReport:
    """What a load did — for the command to print and the tests to assert on."""

    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deactivated: list[str] = field(default_factory=list)

    #: Rooms that were loaded but will never move a ladder, because they draw
    #: from more than one category (``Room.is_rated``). Not an error — a mixed
    #: room is a legitimate thing to author — so it is reported rather than
    #: refused, and the command prints it beside the deactivations.
    unrated: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        line = (
            f"{len(self.created)} created, {len(self.updated)} updated, "
            f"{len(self.deactivated)} deactivated"
        )
        # Only when there are any: a counter reading zero on every run is the
        # fastest way to teach somebody to stop reading the line.
        if self.unrated:
            line += f", {len(self.unrated)} unrated"
        return line


def _read_specs(*, path: Path) -> list[RoomSpec]:
    """Every room in the file, or a refusal listing every problem in it.

    Problems are collected rather than raised at the first one, for the reason
    every loader here does it: somebody fixing a batch wants the whole list in
    one run.
    """
    if not path.exists():
        raise ValidationFailed(f"Resource file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        # An empty file is a deliberate "no rooms", not a malformed one — it is
        # how a deployment turns the lobby off without deleting anything.
        return []
    if not isinstance(raw, list):
        raise ValidationFailed(f"{path.name} must be a list of rooms.")

    specs, problems = [], []
    for index, entry in enumerate(raw):
        try:
            specs.append(RoomSpec.model_validate(entry))
        except Exception as exc:  # pydantic ValidationError, or a bad mapping
            slug = entry.get("slug", "?") if isinstance(entry, dict) else "?"
            problems.append(f"{path.name}[{index}] ({slug}): {exc}")
    if problems:
        raise ValidationFailed("Invalid rooms.", details=problems)

    duplicates = sorted(
        slug for slug, count in Counter(spec.slug for spec in specs).items() if count > 1
    )
    if duplicates:
        raise ValidationFailed(f"Duplicate room slugs: {', '.join(duplicates)}")

    return specs


def _categories_by_slug(specs: list[RoomSpec]) -> dict[str, Category]:
    """Every category the rooms point at, or a refusal naming the missing ones.

    Rooms are loaded *after* the question catalog for this reason: a room
    pointing at a category with no row behind it is a room that cannot draw a
    board, and creating the category implicitly here would let a typo in a room
    invent a sport.

    Looked up through ``all_objects`` and without filtering on ``is_active``: a
    room may legitimately name a sport that is out of season — the room simply
    draws nothing from it until it is back (``selectors.room_question_pool``
    skips inactive categories at draw time), which is a better answer than
    refusing to load the file.
    """
    wanted = {entry.slug for spec in specs for entry in spec.categories}
    found = {c.slug: c for c in Category.all_objects.filter(slug__in=wanted)}
    missing = sorted(wanted - found.keys())
    if missing:
        raise ValidationFailed(
            f"Unknown categories: {', '.join(missing)}. "
            "Add them to apps/questions/resources/categories.yaml and run "
            "sync_questions first."
        )
    return found


@transaction.atomic
def sync_rooms(*, path: Path | None = None) -> LoadReport:
    """Upsert the lobby from ``resources/rooms.yaml``."""
    source = path or ROOMS_FILE
    specs = _read_specs(path=source)
    categories = _categories_by_slug(specs)

    report = LoadReport()
    for spec in specs:
        room, created = Room.all_objects.update_or_create(
            slug=spec.slug,
            defaults={
                "name": spec.name,
                "description": spec.description,
                "question_count_choices": spec.questions_asked_ranges,
                "is_active": spec.is_active,
                "display_order": spec.display_order,
                "logo": spec.logo,
                "color": spec.color,
                # A room that was soft-deleted and is back in the file is being
                # un-deleted, not duplicated: the unique index still holds its
                # slug, so the row has to be revived rather than inserted.
                "deleted_at": None,
            },
        )
        _write_categories(room=room, spec=spec, categories=categories)
        (report.created if created else report.updated).append(spec.slug)

        # Said at authoring time, which is the only moment somebody can still
        # change their mind cheaply. A room drawing from several categories
        # cannot be rated — a rating is per category and a result moves exactly
        # one ladder, so scoring the first for questions that came from the
        # second would be a lie (`Room.is_rated`). The *categories* are
        # untouched by this: their ladders are as real as ever, this room's
        # matches simply never move one.
        if len(spec.categories) > 1:
            report.unrated.append(spec.slug)
            named = ", ".join(entry.slug for entry in spec.categories)
            logger.warning(
                "Room draws from several categories and will not be rated",
                room=spec.slug,
                count=len(spec.categories),
                reason=(
                    f"draws from {named}; a result moves one ladder, so matches "
                    "here are played unrated"
                ),
            )

    seen = {spec.slug for spec in specs}
    stale = Room.objects.filter(is_active=True).exclude(slug__in=seen)
    report.deactivated = sorted(stale.values_list("slug", flat=True))
    stale.update(is_active=False)

    logger.info("Rooms synced", summary=str(report), file=source.name)
    return report


def _write_categories(
    *, room: Room, spec: RoomSpec, categories: dict[str, Category]
) -> None:
    """Replace a room's category list.

    Wholesale, and ``order`` is the file's order rather than an authored number
    — the same rule every position on this platform follows, and the reason a
    resource file cannot leave a gap in one. Position 1 is the room's
    ``primary_category`` — what a match played here is filed under, and the
    ladder it moves when the room draws from that category alone
    (``Room.is_rated``).
    """
    room.categories.all().delete()
    RoomCategory.objects.bulk_create(
        RoomCategory(
            room=room,
            category=categories[entry.slug],
            filter_tags=entry.filter_tags,
            order=order,
        )
        for order, entry in enumerate(spec.categories, start=1)
    )
