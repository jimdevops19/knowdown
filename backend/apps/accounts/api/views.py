"""Auth views: the doors into the platform.

Thin, like every view here — parse, call one service, answer — with two things
that are the view layer's own business and nowhere else's:

* **the refresh token never appears in a response body.** It moves into an
  HttpOnly cookie scoped to the two routes that read it, so a script running on
  the page can only ever reach the short-lived access token;
* **an attempt is logged.** SimpleJWT fires neither ``user_logged_in`` nor
  ``user_login_failed``, so a sign-in that is not logged here is not logged at
  all.
"""

from __future__ import annotations

from dj_rest_auth.jwt_auth import (
    CookieTokenRefreshSerializer,
    get_refresh_view,
    set_jwt_refresh_cookie,
    unset_jwt_cookies,
)
from dj_rest_auth.views import LogoutView
from django.conf import settings
from django.urls.exceptions import NoReverseMatch
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenViewBase

from apps.accounts import services as account_services
from apps.accounts.models import User
from apps.accounts.services import lockout
from apps.core_common.exceptions import ValidationFailed
from shared.logging import get_logger, labels

from .serializers import (
    AuthConfigSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)

logger = get_logger(__name__)


def _client_ip(request) -> str | None:
    """The caller's address as far as this deployment can tell.

    The same identity DRF's own throttles key on, so the two limits guarding
    sign-in agree about who is calling. Only as trustworthy as what reaches
    Django — see ``TRUSTED_PROXY_HOPS`` and ``LOGIN_LOCKOUT_BY_IP``.
    """
    return BaseThrottle().get_ident(request)


def _issue_refresh_cookie(response) -> None:
    """Move the refresh token out of the body and into the HttpOnly cookie.

    dj-rest-auth's own views do this for themselves (``JWT_AUTH_HTTPONLY``).
    Sign-in and sign-up below are plain DRF views it never wraps, so they do it
    by hand — and both, since a refresh token left in the body of *either* is a
    week-long credential sitting in reach of any script on the page.
    """
    if response.status_code in (200, 201) and "refresh" in getattr(response, "data", {}):
        set_jwt_refresh_cookie(response, response.data["refresh"])
        del response.data["refresh"]


class LoginView(TokenViewBase):
    """``POST /api/v1/auth/token/`` — email and password for a token pair.

    Two limits hold this door and they answer different questions. The
    ``login`` throttle scope caps how *fast* one client may post here, rather
    than letting sign-in ride the ``anon`` ceiling that is sized for browsing.
    ``services.lockout`` caps how many times one *address* may be wrong before
    the door shuts at all — the limit that still means something when the
    caller changes IP.

    The lockout is checked before the password is, so a locked address costs a
    guesser a 429 and no hash.
    """

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(tags=["auth"])
    def post(self, request, *args, **kwargs) -> Response:
        typed = str(request.data.get("email", ""))
        ip = _client_ip(request)
        lockout.guard(email=typed, ip=ip)
        try:
            response = super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            # Logged without the address: a log file full of "wrong password for
            # x@y.com" is the same account-existence oracle the response body
            # refuses to be, only written down.
            logger.warning("Sign-in failed", auth_method="password")
            lockout.record_failure(email=typed, ip=ip)
            raise
        logger.info("User signed in", auth_method="password")
        lockout.record_success(email=typed, ip=ip)
        return response

    def finalize_response(self, request, response, *args, **kwargs):
        _issue_refresh_cookie(response)
        return super().finalize_response(request, response, *args, **kwargs)


class RegisterView(APIView):
    """``POST /api/v1/auth/registration/`` — email and password, and that is
    the whole form. The display name is picked afterwards, on its own screen,
    through ``PATCH /api/v1/players/me/``.

    Answers with the same token pair sign-in does, so a new account is usable
    without a second round trip.

    Throttled on the ``login`` scope alongside sign-in: they are the same door
    from an abuse point of view — one guesses at accounts, the other creates
    them — and an unthrottled signup is a way to fill a table from one client.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(tags=["auth"], request=RegisterSerializer, responses=None)
    def post(self, request, *args, **kwargs) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = TokenObtainPairSerializer.get_token(user)
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)},
            status=status.HTTP_201_CREATED,
        )

    def finalize_response(self, request, response, *args, **kwargs):
        _issue_refresh_cookie(response)
        return super().finalize_response(request, response, *args, **kwargs)


class MeView(RetrieveUpdateAPIView):
    """``GET``/``PATCH /api/v1/auth/me/`` — the caller's own account.

    **The only endpoint in the API that may emit an email address**, and narrow
    twice over: ``IsAuthenticated``, and ``get_object`` answers with
    ``request.user``, so the only address it can ever return is the caller's.
    """

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self) -> User:
        return self.request.user


class AuthConfigView(APIView):
    """``GET /api/v1/auth/config/`` — which sign-in methods this tier offers.

    The client draws its sign-in screen from this, so a backend with no Google
    credentials shows a disabled button with a reason rather than a broken one,
    and hides the email forms entirely where the routes behind them are not
    mounted. Unauthenticated by necessity — it is what the sign-in screen asks
    before it can draw itself — and it reveals only which doors exist, never
    anything about who is behind them.
    """

    permission_classes = [AllowAny]

    @extend_schema(tags=["auth"], responses=AuthConfigSerializer)
    def get(self, request, *args, **kwargs) -> Response:
        # The one call a client makes before it can draw the sign-in screen, so
        # this line counts *arrivals* — the denominator for "User signed in",
        # and the only way to see the people who opened the door and left.
        logger.info(
            "Sign-in screen opened",
            auth_method="+".join(
                method
                for method, enabled in (
                    ("password", settings.PERMIT_PASSWORD_AUTH),
                    ("google", settings.GOOGLE_OAUTH_ENABLED),
                )
                if enabled
            )
            or "none",
            anonymous=not request.user.is_authenticated,
        )
        return Response(
            AuthConfigSerializer(
                {
                    "password_enabled": settings.PERMIT_PASSWORD_AUTH,
                    "google_enabled": settings.GOOGLE_OAUTH_ENABLED,
                }
            ).data
        )


class PasswordResetRequestView(APIView):
    """``POST /api/v1/auth/password/reset/`` — ask for a link.

    Answers the same generic 200 whether or not the address matches an account
    with a usable password; the branching happens invisibly inside
    ``services.request_password_reset``.

    Its own throttle scope rather than ``login``'s: this one sends real mail on
    every hit rather than only checking a hash, so it needs a tighter ceiling —
    otherwise it is a way to walk a mailing list from one client.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    @extend_schema(tags=["auth"], request=PasswordResetRequestSerializer, responses=None)
    def post(self, request, *args, **kwargs) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_services.request_password_reset(email=serializer.validated_data["email"])
        return Response(
            {"detail": "If an account exists for that address, we've sent a reset link."}
        )


class PasswordResetConfirmView(APIView):
    """``POST /api/v1/auth/password/reset/confirm/`` — spend a link.

    Unlike the request half this one can answer honestly: a link is either good
    or it is not, and by the time somebody holds a token there is nothing left
    to enumerate.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    @extend_schema(tags=["auth"], request=PasswordResetConfirmSerializer, responses=None)
    def post(self, request, *args, **kwargs) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_services.reset_password(
            uidb64=serializer.validated_data["uid"],
            token=serializer.validated_data["token"],
            new_password=serializer.validated_data["new_password1"],
        )
        return Response({"detail": "Your password has been reset. You can now sign in."})


class _RefreshSerializer(CookieTokenRefreshSerializer):
    """dj-rest-auth's cookie-reading refresh serializer, with one hole closed.

    SimpleJWT looks the token's subject up with a bare ``objects.get()`` and
    lets ``User.DoesNotExist`` out, so a refresh token whose account has since
    been deleted crashes the endpoint with a 500 instead of being refused. A
    token naming nobody is simply not a valid token, so it gets the 401 an
    expired one gets — and a client reads a 401 as "session over" and a 5xx as
    "backend unreachable, retry", which is the difference between signing out
    and a permanent retry loop.
    """

    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except User.DoesNotExist:
            raise InvalidToken("No active account found for the given token.") from None


class RefreshView(get_refresh_view()):
    """``POST /api/v1/auth/token/refresh/`` — rotate the refresh cookie.

    The cookie handling — read the token from the cookie, write the rotated one
    back, keep it out of the body — is dj-rest-auth's; only the serializer
    above is ours.
    """

    serializer_class = _RefreshSerializer

    @extend_schema(tags=["auth"])
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        # A refused refresh means the cookie in the browser is spent — expired,
        # blacklisted, or naming an account that no longer exists. Clearing it
        # stops every later page load posting the same dead token.
        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            unset_jwt_cookies(response)
        return super().finalize_response(request, response, *args, **kwargs)


@extend_schema(tags=["auth"], request=None, responses=None)
class AccountLogoutView(LogoutView):
    """``POST /api/v1/auth/logout/`` — unset the refresh cookie, blacklist the
    token, and say so in the logs.

    The user is read *before* the parent runs: by the time it returns, the
    request's credentials are gone and there is nobody left to name.
    """

    def post(self, request, *args, **kwargs):
        who = labels.user(request.user)
        response = super().post(request, *args, **kwargs)
        # Only a sign-out that happened: the parent *returns* a 401 rather than
        # raising when there is no token to blacklist, and a refused call is not
        # somebody leaving.
        if response.status_code < 400:
            logger.info("User signed out", anonymous=who is None)
        return response

    def get(self, request, *args, **kwargs):
        """dj-rest-auth answers a GET here as a sign-out too, on an
        ``ACCOUNT_LOGOUT_ON_GET`` flag. A GET that revokes a credential is a
        thing any prefetching browser or link scanner can trigger, so this one
        is a 405 instead."""
        from rest_framework.exceptions import MethodNotAllowed

        raise MethodNotAllowed("GET")


class GoogleLoginView(APIView):
    """``POST /api/v1/auth/google/`` — a Google token for Knowdown tokens.

    Deliberately not mounted as a bare ``SocialLoginView``: allauth is a *web*
    library underneath, and whenever it decides a social login cannot complete
    straight through it answers with a redirect to one of its own HTML pages.
    This deployment routes none of them, so such a redirect surfaces as
    ``NoReverseMatch`` — a 500 on the sign-in endpoint for what is really "we
    can't sign you in like this". ``SocialAccountAdapter`` heads off the two
    cases we know of; the catch below turns any new one into a 400 a person can
    read and a log line naming it.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(tags=["auth"], request=None, responses=None)
    def post(self, request, *args, **kwargs):
        if not settings.GOOGLE_OAUTH_ENABLED:
            # With no app registered, allauth fails deep downstream with an
            # opaque error; say plainly that this deployment is not configured.
            logger.warning(
                "Google sign-in attempted but not configured", auth_method="google"
            )
            raise ValidationFailed(
                "Google sign-in is not configured on this server.",
                code="google_oauth_not_configured",
            )

        # Imported here, not at module scope: the provider's view chain reaches
        # into allauth's app registry, and this module is imported by the URLconf
        # on every tier — including the ones with no Google app configured.
        from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
        from dj_rest_auth.registration.views import SocialLoginView

        class _GoogleLogin(SocialLoginView):
            adapter_class = GoogleOAuth2Adapter
            permission_classes = [AllowAny]

        try:
            response = _GoogleLogin.as_view()(request._request, *args, **kwargs)
        except NoReverseMatch:
            logger.exception(
                "Google sign-in needed a page this API doesn't serve",
                auth_method="google",
            )
            raise ValidationFailed(
                "We couldn't complete your Google sign-in. Please try again.",
                code="google_signin_incomplete",
            ) from None
        if response.status_code < 400:
            logger.info("User signed in", auth_method="google")
        return response
