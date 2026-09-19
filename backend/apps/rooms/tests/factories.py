"""Room rows, built directly.

The loader has its own suite (``test_sync``); everything else wants *a room
shaped like this* in as few lines as possible, and going through YAML to get
one would make every selector test a loader test too.
"""

from __future__ import annotations

from apps.categories.models import Category
from apps.rooms.models import Room, RoomCategory

__all__ = ["make_room"]


def make_room(
    *,
    slug: str = "test-room",
    name: str | None = None,
    counts: list[int] | None = None,
    categories: list[tuple[Category, dict]] | None = None,
    **fields,
) -> Room:
    """A saved room with its categories, numbered the way the loader numbers
    them — list order, starting at 1, so position 1 is ``primary_category``."""
    room = Room.objects.create(
        slug=slug,
        name=name or slug.replace("-", " ").title(),
        question_count_choices=counts if counts is not None else [3],
        **fields,
    )
    for order, (category, filter_tags) in enumerate(categories or [], start=1):
        RoomCategory.objects.create(
            room=room, category=category, filter_tags=filter_tags, order=order
        )
    return room
