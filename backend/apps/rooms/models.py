"""A **room** — the settings a game is played under, named and joinable.

Until now the only thing a player picked was a *category*, and everything else
about the match was the engine's own default: how many questions, drawn from
where, at what difficulty. A room is that whole set of choices made once,
given a name, and offered as a thing to join — "NBA", "2000s Finals", "Ball
Knowledge Mixed" — which is why the lobby shows rooms rather than sports.

Two rows, because a room draws from *several* categories and filters each one
differently:

- :class:`Room` is the room itself — its name, its slug, and how long a match
  in it runs (``question_count_choices``).
- :class:`RoomCategory` is one category this room draws from, plus the
  ``filter_tags`` narrowing it. A room with three of these is a room whose
  board can mix three sports; one with a single untagged entry is exactly the
  old "pick a category" behaviour, said out loud.

Authored the same way a question or a badge is — ``resources/rooms.yaml`` plus
``manage.py sync_rooms`` — upserted on ``slug``, deactivated rather than
deleted, because a matchup already played in a room points at that row.

The **question pool** a room implies is not stored anywhere: it is computed at
draw time from these rows (``apps.rooms.selectors.room_question_pool``). A
frozen pool would go stale the moment a question was authored into one of the
room's categories, and the catalog is edited far more often than a room is.
"""

from __future__ import annotations

from django.db import models

from apps.core_common.models import BaseModel, SluggedModel


class Room(SluggedModel, BaseModel):
    """A named set of match settings players can join."""

    name = models.CharField(max_length=100, unique=True)

    #: The stable key everything else names this room by — the URL a player
    #: joins on, the matchmaking pool's key, and what ``rooms.yaml`` upserts
    #: on. Permanent for the same reason a category's slug is: renaming one
    #: orphans every link into it.
    slug = models.SlugField(max_length=100, unique=True)

    description = models.TextField(blank=True)

    #: The match lengths this room runs, authored as ``questions_asked_ranges``
    #: — one is drawn at random per matchup, exactly the way
    #: ``apps.matches.constants.MATCH_QUESTION_COUNTS`` is drawn from for a
    #: room-less match. A **list of allowed counts**, not a low/high pair: a
    #: room that plays 4, 5 or 6 questions is saying those three numbers, and a
    #: range would also promise every value between two bounds a room may not
    #: want (nobody asks for "somewhere between 3 and 11").
    #:
    #: Stored as JSON rather than as rows of a child table because it is read
    #: and written whole, is never queried across rooms, and has no identity of
    #: its own — the same reasoning as a question's ``tags``.
    question_count_choices = models.JSONField(default=list)

    #: Off means "not joinable" — a room out of season or still being
    #: authored. Deliberately not a delete: matchups already played in it
    #: point at this row.
    is_active = models.BooleanField(default=True)

    #: Lower sorts first in the lobby. Authored, because the order rooms are
    #: offered in is an editorial decision ("NBA first, the themed rooms
    #: after") and alphabetical would make it an accident of naming.
    display_order = models.PositiveSmallIntegerField(default=0)

    #: Which badge the room's ball wears — a key from
    #: ``constants.ROOM_LOGO_KEYS``, or blank for a plain ball. Optional
    #: either way: the room's name is set *under* the ball in the lobby, so a
    #: logo adds a mark rather than replacing the name. The client owns the artwork
    #: (`frontend/src/components/icons/roomLogos.tsx`); this column only ever
    #: carries the key, the same split ``players.Player.mascot`` draws.
    logo = models.CharField(max_length=50, blank=True, default="")

    #: Which hue the room's ball is drawn in — a key from
    #: ``constants.ROOM_BALL_COLOR_KEYS``, or blank for "cycle the default
    #: four by position" (the client's own rule, `RoomCircles.ballColor`).
    #: Same split as ``logo``: the gradients live in
    #: `frontend/src/components/avatars/RoomBall.tsx`, this column only ever
    #: carries the key.
    color = models.CharField(max_length=20, blank=True, default="")

    class Meta(BaseModel.Meta):
        ordering = ("display_order", "name")

    def __str__(self) -> str:
        return self.name

    @property
    def primary_category(self):
        """The first category this room draws from — the room's *rating scope*.

        Every matchup carries a category — it is what a match is filed under,
        and for a single-category room it is also the ladder the result moves
        (see :attr:`is_rated`). The first is the room's own answer to which
        one that is: the order in ``rooms.yaml`` is authored, so a room says
        which sport it is really about by listing it first. A mixed room still
        has one, so its matches are still filed somewhere sensible; it just
        does not score it.

        ``None`` only for a room with no categories at all, which the loader
        refuses — so every synced room has one.
        """
        entry = self.categories.select_related("category").first()
        return entry.category if entry is not None else None

    @property
    def is_rated(self):
        """Whether a match played here moves a ladder.

        A room drawing from **one** category is rated: every question asked
        belongs to the category the result is scored against, so the rating
        means what it says. A room that mixes two or more is **not** — a
        rating is per category (``apps.rankings``) and a match can only move
        one ladder, so a mixed room would credit an NBA ladder for questions
        that were never about the NBA. Rather than pick a winner between
        "score the primary category anyway" and "invent a ladder per room",
        a mixed room is played for its own sake and nobody's number changes.

        Read once, at ``apps.matches.services.create_matchup``, and frozen
        onto the matchup as ``is_ranked``: re-deriving it later would let an
        edit to ``rooms.yaml`` rewrite what kind of game an already-played
        match was.
        """
        return self.categories.count() == 1


class RoomCategory(models.Model):
    """One category a room draws from, and how it is narrowed.

    No independent existence beyond the (room, category) pair — the same
    reasoning as ``apps.matches.models.PlayerAnswer`` — so it is a plain
    ``models.Model`` rather than a ``BaseModel``: it is rewritten wholesale on
    every sync, and nothing ever points at one.
    """

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="categories")

    #: ``PROTECT`` like every other reference to a category: a sport is
    #: deactivated, never deleted, and a room pointing at a hole is a room that
    #: cannot draw a board.
    category = models.ForeignKey(
        "categories.Category", on_delete=models.PROTECT, related_name="rooms"
    )

    #: The facets a question must carry to be asked here, e.g.
    #: ``{"era": "2000s"}``. Matched on *containment* — a question tagged with
    #: extra facets still qualifies — by ``apps.questions.selectors
    #: .available_questions``, which is the one place tag filtering is
    #: implemented. Empty means the whole category.
    filter_tags = models.JSONField(default=dict, blank=True)

    #: The file's order. Position 1 is the room's ``primary_category``, so this
    #: is load-bearing rather than cosmetic.
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ("order",)
        verbose_name_plural = "room categories"
        constraints = [
            # One entry per category per room: two would mean a question in it
            # is twice as likely to be drawn as one in any other, which is not
            # a weighting anybody authored on purpose.
            models.UniqueConstraint(
                fields=("room", "category"), name="unique_room_category"
            )
        ]

    def __str__(self) -> str:
        return f"{self.room.slug} / {self.category.slug}"
