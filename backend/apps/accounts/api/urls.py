"""Auth routes: the JWT lifecycle, signing up, resetting a password, Google.

Only the routes this API owns are mounted. ``include("dj_rest_auth.urls")``
would pull in ten more — a second sign-in path that skips ``LoginView`` (and so
leaves brute-force attempts unlogged and unlocked), a ``password/reset/`` that
is an unthrottled account-existence oracle, a duplicate of ``me/`` — none of
which anybody here would be able to name, let alone defend.
"""

from __future__ import annotations

from django.conf import settings
from django.urls import path
from rest_framework_simplejwt.views import TokenVerifyView

from .views import (
    AccountLogoutView,
    AuthConfigView,
    GoogleLoginView,
    LoginView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RefreshView,
    RegisterView,
)

app_name = "accounts"

# Unconditional: these carry no password, and a Google-only tier still issues,
# rotates and revokes exactly the same tokens.
urlpatterns = [
    path("token/refresh/", RefreshView.as_view(), name="token-refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token-verify"),
    path("logout/", AccountLogoutView.as_view(), name="logout"),
    path("google/", GoogleLoginView.as_view(), name="google-login"),
    # What the sign-in screen asks before it can draw itself.
    path("config/", AuthConfigView.as_view(), name="config"),
    # The one endpoint in the API that may emit an email address.
    path("me/", MeView.as_view(), name="me"),
]

# The password door, mounted only where the tier offers one — the same
# conditional-mount pattern the admin uses in ``config/urls.py``. A tier
# without it leaves these 404: no sign-in attempt to throttle, no account to
# enumerate, and nothing in the generated OpenAPI document pointing at either.
# A client hides its email forms off the same flag, reported by
# ``GET /api/v1/auth/config/``.
if settings.PERMIT_PASSWORD_AUTH:
    urlpatterns += [
        path("token/", LoginView.as_view(), name="token-obtain-pair"),
        path("registration/", RegisterView.as_view(), name="register"),
        path("password/reset/", PasswordResetRequestView.as_view(), name="password-reset"),
        path(
            "password/reset/confirm/",
            PasswordResetConfirmView.as_view(),
            name="password-reset-confirm",
        ),
    ]
