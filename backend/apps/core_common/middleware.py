"""Cross-cutting HTTP middleware owned by core_common."""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from shared.admin_url import redact_ops_path
from shared.logging import (
    get_logger,
    get_request_id,
    labels,
    new_request_id,
    set_client_ip,
    set_request_id,
)
from shared.net import client_ip

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """Assigns each request a correlation id, and stocks the log context.

    Honors an inbound ``X-Request-ID`` (e.g. from an upstream proxy) or mints a
    new one, exposes it on ``request.request_id`` and the log context, and echoes
    it back on the response.

    The caller's IP is resolved here too and published into the same per-request
    context (``shared.logging.context``), so *every* line the request causes —
    not only the access-log line — carries it. See ``shared.logging.formatter``
    for why it lands as a base key rather than a field each call site has to
    remember to pass, and ``shared.net`` for why ``TRUSTED_PROXY_HOPS`` is 0 by
    default.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        set_request_id(request_id)
        request.request_id = request_id

        ip = client_ip(request, trusted_hops=settings.TRUSTED_PROXY_HOPS)
        set_client_ip(ip)
        request.client_ip = ip

        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = get_request_id()
        return response


# The platform checking on itself. A kubelet probes every pod every few seconds,
# which on an idle cluster is almost the whole access log — logged as ordinary
# anonymous traffic it drowns the visits that came from an actual browser.
# Matched on the route *name* rather than the path so it holds wherever the
# health urls are mounted (apps.core_common.api.urls).
PROBE_ROUTES = frozenset({"health", "health-ready", "health-live"})

CALLER_USER = "user"
CALLER_PROBE = "probe"


class AccessLogMiddleware:
    """One structured log line per HTTP request — the traffic ledger.

    This is where "how many people did X, and how many of them were signed in?"
    is answered: every request records the route it entered, its method, and
    whether the caller was authenticated. Anonymous visits are called out with
    ``anonymous=True`` so they can be counted apart from signed-in traffic, and a
    redirect records where it sent the caller.

    **The message is a sentence, not a category.** A fixed string like "Request
    handled" says nothing on its own: every answer would live in the fields, so a
    human tailing the log sees a wall of identical lines. Each line names who
    called, what they asked for and what they got, and keeps every field anyway,
    so the queries work and the line is readable without them.

    **``caller`` separates people from machinery.** ``anonymous`` answers "was
    this person signed in"; it cannot answer "was this a person at all", and a
    health probe answers it as anonymous traffic. ``caller="probe"`` names the
    kubelet, and a *successful* probe drops to DEBUG — invisible at the default
    level — while a failing one stays loud at WARNING, because a probe that
    starts answering 503 is exactly the line worth keeping.

    Sits *inside* ``RequestIDMiddleware`` so every line it writes carries the
    same request id as the work it describes.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        self._log(request, response)
        return response

    @staticmethod
    def _log(request: HttpRequest, response: HttpResponse) -> None:
        user = getattr(request, "user", None)
        is_authenticated = bool(user and user.is_authenticated)
        # ``resolver_match`` is populated once the URL has resolved, so the named
        # route is only knowable here on the way out (None for a 404 that matched
        # no pattern at all).
        match = getattr(request, "resolver_match", None)
        route = match.view_name if match else None
        is_probe = bool(route) and route.rsplit(":", 1)[-1] in PROBE_ROUTES
        # Redacted: a request that reached the admin carries the live window's
        # token in its path, and the log must not be a second copy of the
        # credential (shared.admin_url.redact_ops_path).
        path = redact_ops_path(request.path)

        fields: dict[str, object] = {
            "method": request.method,
            "path": path,
            "route": route,
            "status_code": response.status_code,
            "anonymous": not is_authenticated,
            "caller": CALLER_PROBE if is_probe else CALLER_USER,
        }
        if is_authenticated:
            fields["user"] = labels.user(user)

        if 300 <= response.status_code < 400 and response.get("Location"):
            fields["redirect_to"] = response["Location"]

        message = _sentence(
            actor=_actor(
                is_probe=is_probe, is_authenticated=is_authenticated, user=user
            ),
            verb="checked" if is_probe else "requested",
            method=request.method,
            path=path,
            route=route,
            status_code=response.status_code,
            redirect_to=fields.get("redirect_to"),
        )

        if not is_probe:
            logger.info(message, **fields)
        elif response.status_code >= 400:
            # A probe that stopped passing is the one probe line worth reading.
            logger.warning(message, **fields)
        else:
            logger.debug(message, **fields)


def _actor(*, is_probe: bool, is_authenticated: bool, user: object) -> str:
    if is_probe:
        return "Health probe"
    if is_authenticated:
        return f"Signed-in user {labels.user(user)}"
    return "Anonymous visitor"


def _sentence(
    *,
    actor: str,
    verb: str,
    method: str | None,
    path: str,
    route: str | None,
    status_code: int,
    redirect_to: object,
) -> str:
    """The line as a person would say it: who did what, where, and what came back.

    The route name is appended when the url resolved because it is the closest
    thing the server has to *which screen this was* —
    ``/api/v1/categories/nba/`` is where, ``category-detail`` is what.
    """
    where = f"{path} [{route}]" if route else path
    if redirect_to:
        outcome = f"and was redirected ({status_code}) to {redirect_to}"
    else:
        outcome = f"and got {status_code}"
    return f"{actor} {verb} {method} {where} {outcome}"
