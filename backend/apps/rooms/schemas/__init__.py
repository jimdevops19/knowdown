"""The shape of ``resources/rooms.yaml``.

Pydantic rather than a DRF serializer for the reason ``apps.questions.schemas``
is: this validates a *file* a person wrote, not a request. Strict
(``extra="forbid"``) so a misspelled key is a load error rather than a setting
that silently did nothing — a room whose ``filter_tags`` were ignored is a room
that quietly plays the whole category.

    - name: NBA
      slug: nba-room-general
      questions_asked_ranges: [4, 5, 6]
      categories:
        - slug: nba
          filter_tags:
            era: 2000s
        - slug: premier-league   # no filter_tags — the whole category
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.rooms.constants import (
    MAX_ROOM_QUESTION_COUNT,
    MIN_ROOM_QUESTION_COUNT,
    ROOM_BALL_COLOR_KEYS,
    ROOM_LOGO_KEYS,
)

__all__ = ["RoomCategorySpec", "RoomSpec"]

_SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class RoomCategorySpec(BaseModel):
    """One category a room draws from, and the tags narrowing it."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=_SLUG_PATTERN, max_length=100)

    #: Left out entirely — the common case — means the whole category.
    filter_tags: dict[str, str] = Field(default_factory=dict)

    @field_validator("filter_tags", mode="before")
    @classmethod
    def _stringify(cls, value):
        """Accept ``era: 2000`` and ``qualified: true`` as the strings a
        question's ``tags`` actually holds.

        YAML types an unquoted ``2000`` as an int and ``true`` as a bool, and a
        filter that is int-2000 can never match a tag that is str-"2000" — the
        room would simply never draw a question, which is the failure mode
        hardest to notice. Coerced here rather than refused, because the file is
        obviously right and the quoting is YAML's business, not the author's.
        """
        if not isinstance(value, dict):
            return value
        return {
            key: ("true" if item is True else "false" if item is False else str(item))
            for key, item in value.items()
        }

    @field_validator("filter_tags")
    @classmethod
    def _keys_are_addressable(cls, value: dict[str, str]) -> dict[str, str]:
        """The same rule ``apps.questions.selectors.available_questions``
        enforces at draw time, moved to where an author can still fix it.

        A JSON key path containing a digit addresses an *array index*, so a
        facet named ``2000s`` would match nothing at all. Refusing at load time
        turns a room that quietly never starts into a file that will not load.
        """
        bad = sorted(
            key for key in value if not key.replace("_", "").replace("-", "").isalpha()
        )
        if bad:
            raise ValueError(
                f"filter_tags keys must be alphabetic (with - or _): {', '.join(bad)}"
            )
        return value


class RoomSpec(BaseModel):
    """One entry in ``resources/rooms.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(pattern=_SLUG_PATTERN, max_length=100)
    description: str = ""

    #: The authored spelling of ``Room.question_count_choices``. Kept as the
    #: file's own word rather than renamed to match the column: the YAML is the
    #: surface people write, and ``services.sync`` is a small enough seam to
    #: hold the one translation.
    questions_asked_ranges: list[int] = Field(min_length=1)

    categories: list[RoomCategorySpec] = Field(min_length=1)

    is_active: bool = True
    display_order: int = Field(default=0, ge=0)

    #: A key from ``constants.ROOM_LOGO_KEYS``, or left out for "no logo" —
    #: the ball letters the room's name instead. See the comment above
    #: ``logo:`` in ``rooms.yaml`` for where the artwork behind a key lives.
    logo: str = ""

    #: A key from ``constants.ROOM_BALL_COLOR_KEYS``, or left out for "cycle
    #: the default four by position." See the comment above ``color:`` in
    #: ``rooms.yaml`` for where the confirmed palette lives.
    color: str = ""

    @field_validator("logo")
    @classmethod
    def _known_logo(cls, value: str) -> str:
        if value and value not in ROOM_LOGO_KEYS:
            raise ValueError(
                f"Unknown logo {value!r}. Known logos: {', '.join(sorted(ROOM_LOGO_KEYS))}. "
                "Add the artwork to frontend/src/components/icons/roomLogos.tsx and its key "
                "to apps.rooms.constants.ROOM_LOGO_KEYS first."
            )
        return value

    @field_validator("color")
    @classmethod
    def _known_color(cls, value: str) -> str:
        if value and value not in ROOM_BALL_COLOR_KEYS:
            raise ValueError(
                f"Unknown color {value!r}. Known colors: "
                f"{', '.join(sorted(ROOM_BALL_COLOR_KEYS))}. Add the palette to "
                "frontend/src/components/avatars/RoomBall.tsx and its key to "
                "apps.rooms.constants.ROOM_BALL_COLOR_KEYS first."
            )
        return value

    @field_validator("questions_asked_ranges")
    @classmethod
    def _sane_counts(cls, value: list[int]) -> list[int]:
        """Ascending, distinct, and inside the engine's bounds.

        Distinct because a repeated count is a silent weighting — ``[5, 5, 7]``
        makes a five-question match twice as likely, which nobody writes on
        purpose. Sorted because the list is read by people as "this room plays
        4, 5 or 6", and the draw does not care about the order.
        """
        out_of_range = sorted(
            count
            for count in value
            if not MIN_ROOM_QUESTION_COUNT <= count <= MAX_ROOM_QUESTION_COUNT
        )
        if out_of_range:
            raise ValueError(
                f"questions_asked_ranges must be within "
                f"{MIN_ROOM_QUESTION_COUNT}..{MAX_ROOM_QUESTION_COUNT}, got "
                f"{', '.join(str(count) for count in out_of_range)}"
            )
        duplicates = sorted({count for count in value if value.count(count) > 1})
        if duplicates:
            raise ValueError(
                "questions_asked_ranges must not repeat a count: "
                f"{', '.join(str(count) for count in duplicates)}"
            )
        return sorted(value)

    @field_validator("categories")
    @classmethod
    def _distinct_categories(cls, value: list[RoomCategorySpec]) -> list[RoomCategorySpec]:
        """One entry per category — the ``unique_room_category`` constraint,
        said where the author can read it.

        Two entries for one sport would make its questions twice as likely to be
        drawn as another's. A room that wants two *different* filters of the same
        category is asking for a weighting, which is a feature nobody has asked
        for and would need to be authored as one.
        """
        slugs = [spec.slug for spec in value]
        duplicates = sorted({slug for slug in slugs if slugs.count(slug) > 1})
        if duplicates:
            raise ValueError(f"category listed twice: {', '.join(duplicates)}")
        return value
