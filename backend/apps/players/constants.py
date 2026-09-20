"""The numbers the player identity is measured against."""

from __future__ import annotations

#: The stem every generated name is built on. Deliberately anonymous — a
#: display name is published, and one derived from an address would publish
#: half of a credential (see ``apps.players.models``).
AUTO_NAME_STEM = "player"

#: Hex digits of randomness in a generated name. Wide enough that a fresh
#: signup almost never collides, short enough that the name is readable and
#: obviously temporary.
AUTO_NAME_SUFFIX_LENGTH = 6

#: Every mascot a player may wear, as the keys the client draws.
#:
#: An allow-list rather than a shape check: a key nobody named is a key nobody
#: drew, and it would reach a scoreboard as a blank disc. Refusing it here
#: makes a typo a 400 at the moment somebody makes it, rather than a hole in
#: the ladder a week later.
#:
#: **This list is the mirror of `MARKS` in
#: `frontend/src/components/avatars/marks.ts`.** The drawings live there; only
#: the names live here. Adding a mascot means adding it in both files — there
#: is a skill that walks the whole change: `.claude/skills/mascot-avatars/`.
#:
#: Append-only. The key is what is stored on the row, so re-spelling one
#: silently un-picks every player who chose it.
MASCOT_KEYS = frozenset(
    {
        # The founding sixteen — empty hands.
        "bulldog", "owl", "shark", "bear", "fox", "tiger", "goat", "ram",
        "penguin", "gorilla", "rooster", "ox", "eagle", "frog", "octopus",
        "cat",
        # The second sixteen — a ball each, four to a livery.
        "wolf", "panda", "lion", "raccoon", "husky", "moose", "falcon", "boar",
        "polar-bear", "dolphin", "lynx", "crane", "turtle", "chameleon",
        "crocodile", "parrot",
        # The nine a league is named after.
        "hawk", "hornet", "bull", "horse", "grizzly", "deer", "timber-wolf",
        "pelican", "raptor",
    }
)
