"""The Django admin's URL prefix — generated, not guessed.

`/admin/` is the first path anyone scans for, and the admin is not a DRF view,
so none of the API throttles cover its login form. Two things follow: the admin
is off unless a tier asks for it (``ADMIN_ENABLED``), and where it *is* on it
answers at a 40-character random prefix rather than at its famous one.

Lives in ``shared`` rather than in settings because ``manage.py`` generates the
prefix for ``runserver`` before Django is configured, and settings then reads
the same value back out of the environment.
"""

from __future__ import annotations

import os
import secrets
import string

#: Long enough that guessing it is not a strategy: 36^40 possibilities, and a
#: wrong guess is an ordinary 404 that says nothing about what is behind it.
ADMIN_URL_LENGTH = 40

#: Lowercase + digits — URL-safe with no characters that need escaping, and
#: nothing that changes meaning if a case-insensitive layer touches the path.
_ALPHABET = string.ascii_lowercase + string.digits

#: The environment variable both sides read. ``manage.py`` writes it for
#: ``runserver`` so the prefix survives the autoreloader's child process.
ADMIN_URL_ENV = "ADMIN_URL"


def generate_admin_url(length: int = ADMIN_URL_LENGTH) -> str:
    """A fresh random admin prefix (no slashes)."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def normalize_admin_url(value: str) -> str:
    """Turn a configured prefix into the form ``django.urls.path`` wants.

    Accepts ``admin``, ``/admin``, ``admin/`` and returns ``admin/``.
    """
    return value.strip().strip("/") + "/"


def resolve_admin_url() -> str:
    """The prefix for this process: ``ADMIN_URL`` if set, else a fresh one.

    Falling back to a *generated* value rather than to ``admin/`` is the point
    of the whole module — a deployment that turns the admin on without saying
    where still doesn't get the URL every scanner already knows. Under gunicorn
    each worker generates its own, so an admin nobody configured is effectively
    unreachable rather than quietly exposed; ``manage.py`` avoids that for
    ``runserver`` by seeding the environment once and printing what it chose.
    """
    return normalize_admin_url(os.environ.get(ADMIN_URL_ENV) or generate_admin_url())
