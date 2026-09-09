"""Request-scoped logging context.

A per-request id is stored in a :class:`contextvars.ContextVar` by
``RequestIDMiddleware`` (``apps.core_common.middleware``) and read back here so
every log line — and the error envelope — can be correlated to a single
request, independent of Django's own request/response cycle.

The caller's IP rides the same mechanism, set once per request by the same
middleware. It goes in as a contextvar rather than as a kwarg some call sites
remember to pass, on purpose: a service function five calls deep has no request
object to read it off, and "was this abusive" is a question worth being able to
ask of *any* line, not only the ones a caller thought to tag.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()


def set_client_ip(value: str | None) -> None:
    _client_ip.set(value)


def get_client_ip() -> str | None:
    return _client_ip.get()


class RequestIDFilter(logging.Filter):
    """Injects ``record.request_id`` so formatters can reference it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True
