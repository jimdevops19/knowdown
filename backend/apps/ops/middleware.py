"""The only door into the Django admin in a deployment.

Off unless ``ADMIN_GATE_ENABLED`` — local development reaches the admin at its
mounted prefix as usual, and the middleware removes itself from the chain
entirely (``MiddlewareNotUsed``) rather than checking a flag per request.

With it on, three rules, in this order:

1. ``/_ops/static/…`` — the admin's own CSS and JS. Served only while *some*
   window is open. They can't sit under the token (STATIC_URL is fixed at
   import time), so they are gated on the window's existence instead.
2. The admin's mounted prefix, reached directly — 404. Nothing routes there
   from outside today, and this is what keeps that true if something ever does.
3. ``/_ops/<token>/…`` — matched against the live window. No match, no window,
   or a path underneath that isn't the admin: 404, the same 404 as any other
   unrouted path. A match is rewritten so Django sees an ordinary request:
   ``path_info`` loses the ``/_ops/<token>`` prefix and the script prefix gains
   it, which is what makes ``reverse()`` — every link, every form action and
   the login redirect — come back out carrying the token.

It sits above WhiteNoise so rule 1 can refuse an asset before WhiteNoise
answers it, and above everything that reads ``request.path`` so the rewrite has
happened by the time anything looks.
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpRequest, HttpResponse
from django.urls import get_script_prefix, set_script_prefix
from django.views.defaults import page_not_found

from shared.admin_url import OPS_PATH, OPS_STATIC_PATH
from shared.logging import get_logger

from .services import any_window_live, window_for_token

logger = get_logger(__name__)


class AdminGateMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        if not settings.ADMIN_GATE_ENABLED:
            raise MiddlewareNotUsed
        self.get_response = get_response
        # "/admin/" — settings.ADMIN_URL is normalized to a trailing slash and
        # no leading one (shared.admin_url).
        self.admin_path = "/" + settings.ADMIN_URL
        # Only true where the static files were actually moved under the gate;
        # a tier that left STATIC_URL alone simply has no rule 1.
        self.gates_static = str(settings.STATIC_URL).startswith(OPS_STATIC_PATH)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        path = request.path_info

        if self.gates_static and path.startswith(OPS_STATIC_PATH):
            if not any_window_live():
                return self._not_found(request)
            return self.get_response(request)

        if path.startswith(self.admin_path):
            return self._not_found(request)

        if not path.startswith(OPS_PATH):
            return self.get_response(request)

        token, _, rest = path[len(OPS_PATH):].partition("/")
        window = window_for_token(token)
        if window is None:
            self._log_refusal(request)
            return self._not_found(request)

        rest = "/" + rest
        if not rest.startswith(self.admin_path):
            return self._not_found(request)

        # The script prefix is thread-local and outlives the request, so it is
        # put back: under a real WSGI handler the next request would reset it
        # anyway, but anything else sharing the thread (the test client, a
        # management command) would otherwise start reversing URLs into a
        # window that has closed.
        previous_prefix = get_script_prefix()
        self._rewrite(request, script_name=f"{OPS_PATH.rstrip('/')}/{token}", path_info=rest)
        request.admin_window = window
        try:
            return self.get_response(request)
        finally:
            set_script_prefix(previous_prefix)

    @staticmethod
    def _rewrite(request: HttpRequest, *, script_name: str, path_info: str) -> None:
        """Move the token out of the path and into the script prefix.

        Both halves matter: ``path_info`` is what the URLconf resolves, and the
        script prefix is what ``reverse()`` prepends. Set only the first and
        the admin renders correctly once, then links every user to a 404.
        """
        request.path_info = path_info
        request.path = script_name + path_info
        request.META["SCRIPT_NAME"] = script_name
        request.META["PATH_INFO"] = path_info
        set_script_prefix(script_name + "/")

    @staticmethod
    def _not_found(request: HttpRequest) -> HttpResponse:
        """Django's ordinary 404 — the same page any unrouted path gets.

        Deliberately not a 403: a wrong token must not confirm that a right one
        exists, and a closed window must look no different from a deployment
        that has no admin at all.
        """
        return page_not_found(request, None)

    @staticmethod
    def _log_refusal(request: HttpRequest) -> None:
        logger.violate(
            "Admin gate refused a token",
            path=OPS_PATH,
            method=request.method,
            reason="no live admin window matches this token",
        )
