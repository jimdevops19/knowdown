"""Opening and closing the admin window.

Every caller — the two management commands, the gate middleware — goes through
here, so there is one definition of "live" and one place that hashes a token.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from shared.admin_url import OPS_PATH
from shared.logging import get_logger

from .models import AdminWindow

logger = get_logger(__name__)

#: 32 bytes of urlsafe base64 ≈ 43 characters. Guessing it is not a strategy,
#: and a wrong guess is an ordinary 404 that says nothing about what is behind.
TOKEN_BYTES = 32

#: What `open_admin` defaults to. Long enough to do the thing that needed the
#: admin, short enough that forgetting to close it isn't the security incident.
DEFAULT_MINUTES = 30


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def open_window(*, minutes: int = DEFAULT_MINUTES, opened_by: str = "") -> tuple[AdminWindow, str]:
    """Open the admin for ``minutes`` and return the window with its token.

    Any window already live is closed first: one live token at a time means a
    URL pasted into a terminal three days ago is dead, not merely forgotten.
    The plaintext token is returned rather than stored — this is the only time
    it exists.
    """
    token = secrets.token_urlsafe(TOKEN_BYTES)
    now = timezone.now()
    with transaction.atomic():
        superseded = _live_windows().update(closed_at=now)
        window = AdminWindow.objects.create(
            token_hash=hash_token(token),
            opened_by=opened_by,
            expires_at=now + timedelta(minutes=minutes),
        )
    logger.warning(
        # No token, and no path carrying one — this line is the audit trail,
        # not a second copy of the credential.
        "Admin window opened",
        summary=f"open for {minutes} minutes, opened by {opened_by or 'unknown'}",
        count=superseded,
    )
    return window, token


def close_windows() -> int:
    """Close every live window. Returns how many there were."""
    closed = _live_windows().update(closed_at=timezone.now())
    if closed:
        logger.warning("Admin window closed", count=closed)
    return closed


def window_for_token(token: str) -> AdminWindow | None:
    """The live window this token opens, or None."""
    if not token:
        return None
    return _live_windows().filter(token_hash=hash_token(token)).first()


def any_window_live() -> bool:
    """Is the admin open at all? Gates the static assets, which carry no token.

    The admin's CSS and JS are served from `/_ops/static/`, outside the token
    prefix — Django's STATIC_URL is fixed at import time and cannot carry a
    value that changes every half hour. So they are gated on the *existence* of
    an open window instead: no window, no assets.
    """
    return _live_windows().exists()


def window_url(*, base_url: str, token: str, admin_url: str) -> str:
    """The URL `open_admin` prints — the one place the token is ever shown."""
    return f"{base_url.rstrip('/')}{OPS_PATH}{token}/{admin_url}"


def _live_windows():
    return AdminWindow.objects.filter(closed_at__isnull=True, expires_at__gt=timezone.now())
