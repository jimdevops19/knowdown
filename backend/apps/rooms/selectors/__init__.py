"""The read side of rooms — including the pool a room implies.

The interesting function here is :func:`room_question_pool`. A room is a *set*
of (category, tags) filters, and ``apps.questions.selectors`` already knows how
to turn exactly one of those into questions — so this module is the small
amount of glue that runs it once per entry and concatenates the results, and
nothing about tag matching, activity or level bands is re-implemented here.

Selection lives in ``apps.questions`` and the *composition* of it lives here,
which keeps the dependency pointing one way: rooms read questions; questions
have never heard of a room.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from django.db.models import Prefetch, QuerySet

from apps.core_common.exceptions import NotFound, ValidationFailed
from apps.questions.models import QUESTION_MODELS
from apps.questions.selectors import QuestionRef, available_questions, question_pool
from apps.rooms.models import Room, RoomCategory

__all__ = [
    "active_rooms",
    "get_room_by_slug",
    "room_categories",
    "room_pool_size",
    "room_question_pool",
    "select_room_questions",
]


def active_rooms() -> QuerySet[Room]:
    """Every room a player may currently join.

    ``active`` is what "a room" *means* to anything outside the admin, so the
    filter lives here rather than in each view — no caller can offer a
    half-authored room by forgetting it. The categories come along prefetched
    because every reader of this list (the lobby, the API) wants them.
    """
    return Room.objects.filter(is_active=True).prefetch_related(
        Prefetch(
            "categories",
            queryset=RoomCategory.objects.select_related("category").order_by("order"),
        )
    )


def get_room_by_slug(*, slug: str, include_inactive: bool = False) -> Room:
    """One room, by the name everything else calls it.

    ``include_inactive`` is for callers that must find a room whatever state it
    is in — replaying a finished matchup that was played in a room since taken
    out of the lobby.
    """
    queryset = (
        Room.objects.all().prefetch_related("categories__category")
        if include_inactive
        else active_rooms()
    )
    try:
        return queryset.get(slug=slug)
    except Room.DoesNotExist as exc:
        raise NotFound(f"No room with slug '{slug}'.") from exc


def room_categories(*, room: Room) -> list[RoomCategory]:
    """This room's entries, in the authored order.

    Reads the prefetch when ``active_rooms`` put one there, and falls back to a
    query otherwise, so a caller holding a bare ``Room`` is not a bug.
    """
    return list(room.categories.select_related("category").order_by("order"))


def room_question_pool(*, room: Room) -> list[QuestionRef]:
    """Every question this room may ask, across its categories and filters.

    One ``question_pool`` call per entry, concatenated — which is what makes a
    mixed room a genuine mix: a question is in the pool once per *room entry*
    that admits it, and since a category may appear only once per room (the
    ``unique_room_category`` constraint), that is once, full stop. No
    de-duplication is needed and none is done.

    **Inactive categories are skipped rather than refused.** A room naming a
    sport that has gone out of season keeps working on the ones that have not;
    refusing would take a four-category room out of service because one of them
    is being re-authored. A room whose categories are *all* inactive ends up
    with an empty pool, which ``select_room_questions`` reports as the thing it
    actually is — not enough questions to play.
    """
    pool: list[QuestionRef] = []
    for entry in room_categories(room=room):
        if not entry.category.is_active:
            continue
        pool.extend(
            question_pool(
                category=entry.category,
                # `{}` and `None` mean the same thing to `available_questions`,
                # but passing the empty dict makes "no filter" arrive as data
                # rather than as an absence.
                tags=entry.filter_tags or None,
            )
        )
    return pool


def select_room_questions(
    *,
    room: Room,
    count: int,
    rng: random.Random | None = None,
    choose: Callable[..., list[QuestionRef]] | None = None,
    exclude: set[tuple[str, str]] | None = None,
) -> list[QuestionRef]:
    """Draw ``count`` distinct questions for one matchup in this room.

    The room's analogue of ``apps.questions.selectors.select_questions``, with
    the same three promises, for the same reasons stated there: the **server**
    draws, it draws **once** for both players, and it **refuses** rather than
    playing a shorter match when the pool is too small — the length of a game
    must not depend on how well stocked a room happens to be.

    ``choose`` is the same seam ``select_questions`` offers, and it is how
    ``apps.matches`` biases the draw away from questions either player has
    already been shown (``apps.exposure``) without this module ever importing
    its caller.

    ``exclude`` takes refs out of the pool before the draw — what a tie-breaker
    needs, since the one thing a sudden-death question must not be is a
    question this matchup has already played.
    """
    if count < 1:
        raise ValidationFailed("A matchup needs at least one question.")

    pool = room_question_pool(room=room)
    if exclude:
        pool = [ref for ref in pool if ref.as_tuple() not in exclude]
    if len(pool) < count:
        raise ValidationFailed(
            f"Room '{room.slug}' has {len(pool)} askable questions, "
            f"{count} were requested.",
            code="not_enough_questions",
        )
    if choose is not None:
        return choose(pool=pool, count=count, rng=rng)
    return (rng or random).sample(pool, count)


def room_pool_size(*, room: Room) -> int:
    """How many questions this room could ask, without building the list.

    The same pool ``room_question_pool`` returns, counted in the database
    instead of in Python: the lobby wants the number (a room too thin to fill
    its own shortest match is one a player should not be sent into), and
    hauling every id back to count them is the wrong shape for a list endpoint
    that renders one line per room.
    """
    return sum(
        available_questions(
            model=model, category=entry.category, tags=entry.filter_tags or None
        ).count()
        for entry in room_categories(room=room)
        if entry.category.is_active
        for model in QUESTION_MODELS.values()
    )
