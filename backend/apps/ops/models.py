"""The thing that makes the admin reachable, for half an hour, on purpose.

The Django admin is mounted permanently but answers nowhere a caller can get
to it: ``AdminGateMiddleware`` 404s its mounted prefix outright and only routes
requests that arrive under ``/_ops/<token>/``. An ``AdminWindow`` row *is* that
token — created by ``manage.py open_admin``, expiring on its own clock.

Why a database row rather than an environment variable and a redeploy: opening
the admin must not restart a process every worker inherits differently, must
be seen identically by every worker in every replica, must survive a replica
being rescheduled mid-window, and must leave a record of who opened it and
when. A row does all four; an environment variable does none of them.

The token is stored **hashed**. The plaintext exists exactly once, in the URL
the command prints, so a database dump of a live window still doesn't open it.
Not a ``BaseModel``: soft-deleting a window would leave a closed row that the
default manager hides and the gate still has to reason about, and none of the
UUID/timestamp machinery buys anything here.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class AdminWindow(models.Model):
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    # Free text — whoever ran the command said who they were, or didn't. This
    # is an audit note, not an identity the gate checks.
    opened_by = models.CharField(max_length=254, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    # Set by `manage.py close_admin`, and by `open_admin` on the windows it
    # supersedes. Expiry alone would close a window too; this is the early exit.
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "admin window"

    def __str__(self) -> str:
        state = "live" if self.is_live else "closed"
        return f"admin window opened {self.created_at:%Y-%m-%d %H:%M} ({state})"

    @property
    def is_live(self) -> bool:
        return self.closed_at is None and self.expires_at > timezone.now()
