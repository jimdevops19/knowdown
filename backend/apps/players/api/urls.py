"""Player routes. Read-and-correct-your-own; nothing here creates a player —
registration does that (``accounts.services.register_user``)."""

from __future__ import annotations

from django.urls import path

from .views import DisplayNameAvailableView, PlayerMeView

app_name = "players"

urlpatterns = [
    path("me/", PlayerMeView.as_view(), name="me"),
    # Before `me/`'s sibling routes rather than after: a literal path and a
    # future `<str:display_name>/` must not compete, and the literal wins by
    # being declared first.
    path(
        "display-name-available/",
        DisplayNameAvailableView.as_view(),
        name="display-name-available",
    ),
]
