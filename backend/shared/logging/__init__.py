"""Structured JSON logging, shared by every Django app in the backend.

Public API::

    from shared.logging import get_logger, labels

    logger = get_logger(__name__)
    logger.info("Questions synced", category=labels.category(category), summary=str(report))

See ``logger.py`` for the ``JSONLogger`` class, ``schema.py`` for the whitelist
of extra fields it accepts, ``labels.py`` for the helpers that turn a model into
the readable name a log line should call it by, ``service.py`` for the
``api``/``realtime``/``cli`` label every line carries, ``formatter.py`` for the
JSON line format (wired up in ``config.settings.base.LOGGING``), and
``context.py`` for the request-id contextvar used to correlate log lines to a
single request.
"""

from __future__ import annotations

from . import labels
from .context import (
    RequestIDFilter,
    get_client_ip,
    get_request_id,
    new_request_id,
    set_client_ip,
    set_request_id,
)
from .formatter import JSONFormatter
from .logger import VIOLATE_LEVEL, JSONLogger, get_logger
from .schema import SUPPORTED_LOG_FIELDS, UnsupportedLogFieldError
from .service import SERVICE

__all__ = [
    "JSONFormatter",
    "JSONLogger",
    "RequestIDFilter",
    "SERVICE",
    "SUPPORTED_LOG_FIELDS",
    "UnsupportedLogFieldError",
    "VIOLATE_LEVEL",
    "get_client_ip",
    "get_logger",
    "get_request_id",
    "labels",
    "new_request_id",
    "set_client_ip",
    "set_request_id",
]
