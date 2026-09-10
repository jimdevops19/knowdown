"""The competitor.

A ``Player`` is who appears on a scoreboard; ``accounts.User`` is who signs in.
They are separate rows joined by a nullable one-to-one, which is what lets a
staff account exist without ever entering a matchup, and what keeps the login
credential out of everything the game publishes.

The **display name is not a login and is never seeded from an email address.**
It is printed beside every result, so seeding it from an address would publish
half of somebody's credential, and accepting it at sign-in would hand an
attacker the half they cannot otherwise read. A new player therefore gets a
generated name (``has_auto_name``) and is asked to choose one on its own screen.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.core_common.models import BaseModel


def avatar_upload_to(instance: "Player", filename: str) -> str:
    """``avatars/<player id>/<filename>``.

    Keyed by the player rather than by the original name so two people
    uploading ``avatar.png`` do not fight over one path, and so removing a
    player's pictures is removing one directory.
    """
    return f"avatars/{instance.pk}/{filename}"


class Player(BaseModel):
    """A competitor: a name, a picture, and a link back to an account."""

    #: ``SET_NULL`` rather than ``CASCADE``: a matchup is a thing two people
    #: did, so removing one of them would edit the other's history. The account
    #: really disappears (``accounts.User`` keeps no soft delete); the
    #: competitor stays, holding its side of every result it played.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="player",
    )

    #: Unique platform-wide, compared case-insensitively (see the constraint).
    #: Every write goes through ``services.set_display_name`` — the serializer
    #: field is read-only, so no payload can route around the validator.
    display_name = models.CharField(max_length=30)

    #: True while the name is one the platform generated rather than one the
    #: person chose. The client's cue to ask them for a real one.
    has_auto_name = models.BooleanField(default=True)

    avatar = models.ImageField(upload_to=avatar_upload_to, null=True, blank=True)

    #: A CPU opponent (``manage.py seed_bots``, ``apps.matches.bots``) rather
    #: than a person behind an account. Still an ordinary ``Player`` — it
    #: takes a rating, appears on a scoreboard, and is subject to every
    #: constraint above — because the match/ranking/achievement engines must
    #: not need a special case for who is on the other side of the race. The
    #: one place this flag is read is matchmaking's bot fallback
    #: (``apps.matches.bots.selection``), which draws only from bots; nothing
    #: else in the codebase branches on it.
    is_bot = models.BooleanField(default=False)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["display_name"]),
            models.Index(fields=["is_bot"]),
        ]
        constraints = [
            # Case-insensitive uniqueness *in the database*, not only in the
            # validator: two clients claiming the same free name in the same
            # instant both pass a check that reads before either writes, and
            # the loser must meet a constraint (a 409) rather than a second row.
            # Soft-deleted rows are excluded so a name goes back in the pool.
            models.UniqueConstraint(
                Lower("display_name"),
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_player_display_name",
            )
        ]

    def __str__(self) -> str:
        return self.display_name
