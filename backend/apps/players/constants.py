"""The numbers the player identity is measured against."""

from __future__ import annotations

#: The largest avatar accepted, in bytes. A picture shown at 64px does not need
#: to be bigger than this, and the ceiling is what stops an upload endpoint
#: being a way to fill a disk.
MAX_AVATAR_BYTES = 2 * 1024 * 1024

#: Image formats Pillow must report for an upload to be stored. A list of what
#: is allowed rather than of what is refused: a format nobody named is a format
#: nobody thought about.
ALLOWED_AVATAR_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})

#: The stem every generated name is built on. Deliberately anonymous — a
#: display name is published, and one derived from an address would publish
#: half of a credential (see ``apps.players.models``).
AUTO_NAME_STEM = "player"

#: Hex digits of randomness in a generated name. Wide enough that a fresh
#: signup almost never collides, short enough that the name is readable and
#: obviously temporary.
AUTO_NAME_SUFFIX_LENGTH = 6
