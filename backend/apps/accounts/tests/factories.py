"""Accounts fixtures: one account, made the way the product makes one."""

from __future__ import annotations

from apps.accounts.models import User
from apps.accounts.services import register_user

#: Passes every validator in AUTH_PASSWORD_VALIDATORS, and is obviously not a
#: real password to anyone reading a failure.
PASSWORD = "correct-horse-19"


def make_user(*, email: str = "player@example.com", password: str = PASSWORD) -> User:
    """An account with the ``Player`` registration always gives it."""
    return register_user(email=email, password=password)
