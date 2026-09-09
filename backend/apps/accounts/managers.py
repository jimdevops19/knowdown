"""The manager behind ``createsuperuser`` and every scripted account."""

from __future__ import annotations

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Creates users keyed on an email address rather than a username.

    ``create_user`` accepts **no** email: accounts made from a script, a
    fixture or the sync commands need none, and such an account simply has no
    password door. ``create_superuser`` does require one, because the admin's
    login form and ``createsuperuser`` both key on ``USERNAME_FIELD``.
    """

    use_in_migrations = True

    def _create(self, email: str | None, password: str | None, **extra):
        user = self.model(email=self.normalize_email(email) if email else None, **extra)
        # `set_password` hashes; a user created with password=None gets an
        # unusable one, which is the right state for an account that will only
        # ever sign in through an identity provider.
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str | None = None, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("A superuser must have is_staff and is_superuser set.")
        if not email:
            raise ValueError("A superuser must have an email address.")
        return self._create(email, password, **extra)
