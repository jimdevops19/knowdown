"""Write side for the competitor.

Two rules hold this module together:

- **``set_display_name`` is the only writer of the published name.** The API
  serializer's field is read-only, so a PATCH cannot route around the
  validator, and the shell, the tests and a future admin action all take the
  same door.
- **A generated name is never derived from an account.** See
  ``apps.players.models`` for why an email address may not become one.
"""

from __future__ import annotations

import secrets

from django.db import IntegrityError, transaction

from apps.core_common.exceptions import Conflict, ValidationFailed
from apps.players import selectors, validators
from apps.players.constants import (
    ALLOWED_AVATAR_FORMATS,
    AUTO_NAME_STEM,
    AUTO_NAME_SUFFIX_LENGTH,
    MAX_AVATAR_BYTES,
)
from apps.players.models import Player
from shared.logging import get_logger, labels

logger = get_logger(__name__)

__all__ = [
    "ensure_player_for_user",
    "generate_display_name",
    "set_avatar",
    "set_display_name",
]


def generate_display_name() -> str:
    """A free, obviously temporary name: ``player_9f2c1a``.

    Random rather than counted so it says nothing about how many people have
    signed up, and free at the moment it is returned — the constraint on
    ``Player`` is what settles a race, not this loop.
    """
    while True:
        candidate = (
            f"{AUTO_NAME_STEM}_{secrets.token_hex(AUTO_NAME_SUFFIX_LENGTH)[:AUTO_NAME_SUFFIX_LENGTH]}"
        )
        if not selectors.is_display_name_taken(display_name=candidate):
            return candidate


@transaction.atomic
def ensure_player_for_user(*, user) -> Player:
    """The competitor behind an account, created if this is the first ask.

    Idempotent, and called from every path that can produce an account —
    registration, social sign-in, a shell script — because an account without a
    Player is an account that cannot play and does not appear anywhere.
    """
    player = selectors.player_for_user(user=user)
    if player is not None:
        return player

    for _ in range(5):
        try:
            with transaction.atomic():
                player = Player.objects.create(
                    user=user,
                    display_name=generate_display_name(),
                    has_auto_name=True,
                )
        except IntegrityError:
            # Two signups whose generated names collided, which the constraint
            # settles. Drawing again costs nothing; there is no name here
            # anybody chose, so nobody has to be told.
            continue
        logger.info("Player created", player=labels.player(player), user=labels.user(user))
        return player

    raise Conflict("Could not allocate a display name.", code="display_name_unavailable")


@transaction.atomic
def set_display_name(*, player: Player, display_name: str) -> Player:
    """Claim ``display_name`` — the only way the published name changes.

    Clearing ``has_auto_name`` is as much the point of the write as the name
    is: it is what stops the client asking again.
    """
    display_name = (display_name or "").strip()
    validators.validate_display_name(display_name=display_name, exclude_player=player)

    player.display_name = display_name
    player.has_auto_name = False
    try:
        player.save(update_fields=["display_name", "has_auto_name", "updated_at"])
    except IntegrityError as exc:
        # The validator saw the name free; the constraint did not. A lost race,
        # not a bug — 409, so the client can say "someone just took that".
        raise Conflict(
            "That display name was just taken. Please pick another one.",
            code="display_name_taken",
        ) from exc

    logger.info("Display name changed", player=labels.player(player))
    return player


def set_avatar(*, player: Player, image) -> Player:
    """Store an uploaded picture, or clear the one there.

    Checked before it is written, and checked for what it *is* rather than for
    what it is called: an extension is a claim the uploader makes, and the only
    honest answer comes from decoding the file.
    """
    if image is None:
        player.avatar.delete(save=False)
        player.avatar = None
        player.save(update_fields=["avatar", "updated_at"])
        logger.info("Avatar cleared", player=labels.player(player))
        return player

    if image.size > MAX_AVATAR_BYTES:
        raise ValidationFailed(
            f"That picture is too large. The limit is {MAX_AVATAR_BYTES // (1024 * 1024)} MB.",
            code="avatar_too_large",
        )
    _validate_image_format(image=image)

    player.avatar = image
    player.save(update_fields=["avatar", "updated_at"])
    logger.info("Avatar uploaded", player=labels.player(player))
    return player


def _validate_image_format(*, image) -> None:
    """Refuse anything Pillow will not open, or opens as a format we don't serve."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(image) as opened:
            opened.verify()
            image_format = opened.format
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationFailed(
            "That file isn't an image we can read.", code="invalid_avatar"
        ) from exc
    finally:
        # `Image.open` consumes the upload's stream; anything that reads it
        # afterwards (the storage backend, for one) starts from wherever
        # Pillow stopped unless it is wound back.
        image.seek(0)

    if image_format not in ALLOWED_AVATAR_FORMATS:
        raise ValidationFailed(
            "Avatars must be a JPEG, PNG or WEBP image.", code="invalid_avatar"
        )
