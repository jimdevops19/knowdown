"""Who is allowed into the rehearsal room.

One class, and it is deliberately not spelled ``IsAdminUser``. DRF's own class
would do the ``is_staff`` half of this and nothing else, and the other half —
re-checking the flag that mounted the route — is the part that has to be here
rather than assumed.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import BasePermission

__all__ = ["IsMaintainer"]


class IsMaintainer(BasePermission):
    """A signed-in ``is_staff`` account, on a tier that asked for the tester.

    **``is_staff`` is the whole test, and it is the right one.** It is the flag
    ``manage.py createsuperuser`` sets and nothing else in this platform does:
    registration never sets it, Google sign-in never sets it, and no endpoint
    can be talked into setting it. So "an account somebody made from a shell on
    the box" and "an account that may read answer keys" are the same set, which
    is exactly the boundary asked for. A group or a custom flag would be a
    second thing to keep in step with that one, and a maintainer tool is not
    worth a permissions model.

    **The settings check is redundant, and stays.** With the flag off these URLs
    are not mounted, so this method cannot be reached — until someone mounts the
    routes unconditionally, or includes them from a second URLconf, or a test
    points ``ROOT_URLCONF`` somewhere that does. The cost of the line is one
    attribute lookup per request; the cost of leaving it out is that the day the
    mount changes, the flag silently stops meaning anything.
    """

    message = "The question tester is open to maintainers only."

    def has_permission(self, request, view) -> bool:
        if not settings.TESTER_ENDPOINT_ENABLED:
            return False
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)
