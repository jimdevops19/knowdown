"""The auth identity.

``accounts.User`` is who signs in. It is deliberately **not** the competitor:
``players.Player`` will be the domain identity that carries a display name, an
avatar, a rating and a match history, linked by a nullable one-to-one. Keeping
them apart is what lets a Player exist before its person signs up, and lets a
staff account exist without ever appearing in a matchup.

This is the minimum that has to be settled before the first ``migrate``:
``AUTH_USER_MODEL`` cannot be swapped afterwards without a hand-written
migration or a wiped database. Registration, sign-in, OAuth and JWT endpoints
land with the auth increment; nothing here serves HTTP yet.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from apps.core_common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .managers import UserManager


class User(UUIDPrimaryKeyModel, TimeStampedModel, AbstractBaseUser, PermissionsMixin):
    """An account. The email is the credential; everything else is optional.

    Not a ``BaseModel``: an account is the one row that must really disappear
    when it is deleted, so it takes the UUID pk and the timestamps and leaves
    the soft delete behind.

    ``email`` is **nullable** rather than blank — two address-less accounts must
    not collide on ``unique`` — and it is the only identifier here. A display
    name is the Player's, not the account's; publishing an email in a scoreboard
    would publish half of somebody's credential.
    """

    email = models.EmailField(unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=150, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    #: Nothing beyond the credential is required to make one. `createsuperuser`
    #: asks for USERNAME_FIELD plus this list, and there is nothing else it
    #: could sensibly insist on.
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.email or f"user:{self.pk}"

    def get_full_name(self) -> str:
        return self.full_name or (self.email or "")

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else (self.email or "")
