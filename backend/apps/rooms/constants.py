"""The numbers a room is measured against.

Separate from ``apps.matches.constants.MATCH_QUESTION_COUNTS``, which is what a
match plays when *no* room was chosen. A room states its own lengths, and these
are the bounds any of them must fall inside — a room is a set of settings, not
a way around the engine's limits.
"""

from __future__ import annotations

__all__ = [
    "MAX_ROOM_QUESTION_COUNT",
    "MIN_ROOM_QUESTION_COUNT",
    "ROOM_BALL_COLOR_KEYS",
    "ROOM_LOGO_KEYS",
]

#: The shortest match a room may run. One question is a coin toss, not a race,
#: but it is a legitimate thing to author for a demo or a themed sudden-death
#: room, so the floor is the floor and not an opinion.
MIN_ROOM_QUESTION_COUNT = 1

#: The longest. Well past ``apps.questions.constants
#: .LONGEST_MATCH_QUESTION_COUNT`` (7, what the catalog is stocked to) on
#: purpose: that number says how deep every *level band* must be, while this
#: one only stops a typo — ``questions_asked_ranges: [50]`` — from becoming a
#: room that refuses every draw with "not enough questions" long after the
#: person who wrote it has stopped looking.
MAX_ROOM_QUESTION_COUNT = 20

#: Every logo a room's ball may wear, as the keys ``resources/rooms.yaml``
#: authors under ``logo:``.
#:
#: An allow-list rather than a free string, for the same reason
#: ``apps.players.constants.MASCOT_KEYS`` is one: a key nobody drew is a key
#: that renders nothing, and refusing it at load time makes a typo a failed
#: sync rather than a blank ball discovered days later in the lobby.
#:
#: **This is the mirror of ``ROOM_LOGOS`` in
#: `frontend/src/components/icons/roomLogos.tsx``.** The artwork lives there;
#: only the names live here. Adding a logo means drawing it in that file and
#: adding its key to both places — see the comment above ``logo:`` in
#: ``resources/rooms.yaml`` for the authoring side of this.
#:
#: Append-only, the same as ``MASCOT_KEYS``: a room's ``logo`` is read back out
#: of the database by key, so re-spelling one silently blanks every room that
#: named it.
ROOM_LOGO_KEYS = frozenset({"tv"})

#: Every hue a room's ball may take, as the keys ``resources/rooms.yaml``
#: authors under ``color:``. Confirmed against a rendered preview of all of
#: them before this list was written, the same glossy-sphere gradient the
#: ball actually uses — not picked blind off a color wheel.
#:
#: **This is the mirror of ``PALETTES`` in
#: `frontend/src/components/avatars/RoomBall.tsx``.** The gradients live
#: there; only the names live here, for the same reason ``ROOM_LOGO_KEYS``
#: does. A room author sees the choices by opening that file (or the
#: published preview linked from its comment) — see the note above ``color:``
#: in ``rooms.yaml``.
#:
#: Append-only, same as ``ROOM_LOGO_KEYS``: re-spelling a key silently drops
#: every room that named it back to the default position-cycled rotation.
ROOM_BALL_COLOR_KEYS = frozenset(
    {
        # The founding four.
        "orange", "violet", "pink", "lime",
        # The rest of the confirmed 28.
        "red", "amber", "gold", "yellow", "green", "emerald", "teal", "cyan",
        "sky", "blue", "indigo", "purple", "fuchsia", "rose", "copper",
        "slate",
        # Orange fades.
        "peach", "apricot", "tangerine", "marmalade", "rust", "sunset",
        "honey", "papaya",
    }
)
