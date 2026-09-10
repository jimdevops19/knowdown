"""What a display name may be.

The name is the one thing the platform prints about a person — every
scoreboard, every match history, every ladder row — so the rules here are about
what may be *published*, not about what is safe to store. Shape and availability
are separate functions because they fail differently: a bad shape is the
person's typing, a taken name is somebody else's.
"""

from __future__ import annotations

import re

from apps.core_common.exceptions import ValidationFailed
from apps.players import selectors

DISPLAY_NAME_MIN_LENGTH = 3
DISPLAY_NAME_MAX_LENGTH = 30

#: Letters, digits and underscores, with single spaces allowed between words.
#: No leading, trailing or doubled spaces, and nothing that could be mistaken
#: for another name through invisible or look-alike whitespace.
DISPLAY_NAME_PATTERN = re.compile(
    rf"^(?=.{{{DISPLAY_NAME_MIN_LENGTH},{DISPLAY_NAME_MAX_LENGTH}}}$)"
    r"[A-Za-z0-9_]+( [A-Za-z0-9_]+)*$"
)

#: Names that would read as the platform speaking rather than as a person.
#: Compared lower-cased, like the uniqueness rule beside them.
RESERVED_DISPLAY_NAMES = frozenset(
    {
        "admin", "administrator", "anonymous", "api", "bot", "guest", "help",
        "knowdown", "login", "logout", "me", "mod", "moderator", "none",
        "null", "player", "players", "root", "settings", "signup", "staff",
        "support", "system", "undefined", "unknown", "you",
    }
)

#: Refused wherever they appear, not only as whole names — "xadmin" and
#: "knowdown_official" read as staff just as much as the bare words do.
BLOCKED_SUBSTRINGS = frozenset({"admin", "knowdown"})


def validate_display_name_shape(*, display_name: str) -> None:
    """Everything decidable without the database: charset, length, reservations."""
    if not DISPLAY_NAME_PATTERN.match(display_name or ""):
        raise ValidationFailed(
            f"A display name is {DISPLAY_NAME_MIN_LENGTH}–{DISPLAY_NAME_MAX_LENGTH} "
            "characters of letters, numbers and underscores, with single spaces "
            "allowed between words (not at the start or the end).",
            code="invalid_display_name",
        )
    lowered = display_name.lower()
    if lowered in RESERVED_DISPLAY_NAMES or any(
        word in lowered for word in BLOCKED_SUBSTRINGS
    ):
        raise ValidationFailed(
            f"'{display_name}' is reserved. Please pick another name.",
            code="reserved_display_name",
        )


def validate_display_name_available(*, display_name: str, exclude_player=None) -> None:
    """Nobody else holds this name, compared the way the constraint compares it.

    ``exclude_player`` is what makes a rename to your own capitalisation legal:
    it is a rename to the person and a no-op to the database.
    """
    if selectors.is_display_name_taken(
        display_name=display_name, exclude_player=exclude_player
    ):
        raise ValidationFailed(
            "That display name is taken. Please pick another one.",
            code="display_name_taken",
        )


def validate_display_name(*, display_name: str, exclude_player=None) -> None:
    """Both halves, in the order that gives the more useful message first."""
    validate_display_name_shape(display_name=display_name)
    validate_display_name_available(
        display_name=display_name, exclude_player=exclude_player
    )
