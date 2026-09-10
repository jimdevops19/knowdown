"""Player routes. Read-and-correct-your-own; nothing here creates a player —
registration does that (``accounts.services.register_user``)."""

from __future__ import annotations

from django.urls import path

from .views import DisplayNameAvailableView, PlayerMeView, PlayerProfileView

app_name = "players"

urlpatterns = [
    path("me/", PlayerMeView.as_view(), name="me"),
    # Both literal, and both before `<str:display_name>/`: a literal path and
    # a variable one must not compete, and the literal wins by being declared
    # first — otherwise `/players/me/` would resolve as somebody's profile
    # with the display name "me".
    path(
        "display-name-available/",
        DisplayNameAvailableView.as_view(),
        name="display-name-available",
    ),
    path("<str:display_name>/", PlayerProfileView.as_view(), name="profile"),
]
