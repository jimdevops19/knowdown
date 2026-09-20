"""Who is allowed into the rehearsal room, and who may rewrite it.

Two classes, and the split is between looking and writing.

:class:`IsMaintainer` is deliberately not spelled ``IsAdminUser``: DRF's own
class would do the ``is_staff`` half of this and nothing else, and the other
half — re-checking the flag that mounted the route — is the part that has to be
here rather than assumed.

:class:`CanEditQuestions` guards the three write verbs alone, because what they
change is the repository's YAML rather than a row, and that only means anything
on a tier somebody can commit from.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission

__all__ = ["CanEditQuestions", "IsMaintainer"]


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


class CanEditQuestions(BasePermission):
    """The write half of the tester, on a tier whose file edits mean something.

    Sits *beside* :class:`IsMaintainer` on the two views that write (the
    catalog's ``POST`` and ``QuestionSourceView``'s ``PUT``/``PATCH``) and lets
    every read through untouched — a read-only tester is still the whole
    rehearsal room, and refusing ``GET`` here would take away the page rather
    than its buttons.

    **What it protects is the resource files, not the rows.** ``apps.tester.
    services.authoring`` rewrites a block in ``resources/questions/…`` and
    reloads the catalog from it, so an edit made anywhere but a developer's
    checkout is written into a container's copy of the repo: gone at the next
    deploy, and absent from the pull request that was supposed to carry it. A
    question that is right on staging and wrong in git is worse than one that
    is wrong in both, because only one of them gets noticed.

    The client is told the same thing up front — ``GET /tester/config/`` carries
    ``editable`` — so the buttons arrive greyed rather than failing on click.
    This is the gate; that is the courtesy.
    """

    message = (
        "Questions can't be edited on this deployment — the editor writes to the "
        "questions resource YAML files, so do it from local and commit the change."
    )

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return bool(settings.QUESTION_TESTER_EDITABLE)
