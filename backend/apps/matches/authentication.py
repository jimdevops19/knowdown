"""JWT authentication for the ASGI/WebSocket scope.

The REST API authenticates by Bearer header only (``backend/CLAUDE.md``), but a
browser's ``WebSocket`` constructor cannot set one — the token has to travel in
the URL. ``?token=`` is the accepted trade-off (it can land in a proxy access
log, which is why ``AccessLogMiddleware``/reverse-proxy configs redact query
strings the way ``apps.ops`` redacts the admin token path); the alternative,
the ``Sec-WebSocket-Protocol`` header as a token carrier, needs client-side
support this project is not assuming yet.

This is deliberately a small, hand-rolled middleware rather than
``channels.auth.AuthMiddlewareStack`` — that stack authenticates from a Django
session cookie, which the REST API does not issue (no ``SessionAuthentication``,
same file) and which a WebSocket handshake across origins may not even carry.
The same SimpleJWT access token a client already holds for REST calls is what
it uses here.
"""

from __future__ import annotations

from urllib.parse import parse_qsl

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from shared.logging import get_logger

logger = get_logger(__name__)


@database_sync_to_async
def _user_from_token(token: str):
    from django.contrib.auth import get_user_model

    try:
        validated = AccessToken(token)
    except TokenError:
        return AnonymousUser()

    user_model = get_user_model()
    try:
        # USER_ID_CLAIM/USER_ID_FIELD are both "id" (config.settings.base.SIMPLE_JWT).
        return user_model.objects.get(pk=validated["user_id"])
    except (user_model.DoesNotExist, KeyError):
        return AnonymousUser()


class JWTAuthMiddleware:
    """Resolves ``scope["user"]`` from ``?token=<access token>`` before the
    inner application (a consumer, or ``URLRouter``) ever sees the scope.

    An absent or invalid token resolves to ``AnonymousUser`` rather than
    rejecting the connection here — the same posture DRF's own
    ``IsAuthenticated`` takes at the view layer, so "who are you" and "are you
    allowed to do that" stay two separate questions. A consumer that requires a
    signed-in caller checks ``scope["user"].is_authenticated`` itself and
    closes with its own code (see ``consumers.py``).
    """

    def __init__(self, inner) -> None:
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode("utf-8", errors="ignore")
        token = dict(parse_qsl(query_string)).get("token")
        scope["user"] = await _user_from_token(token) if token else AnonymousUser()
        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner):  # noqa: N802 - matches Channels' own naming
    return JWTAuthMiddleware(inner)
