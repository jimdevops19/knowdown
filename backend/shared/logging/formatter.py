"""JSON log formatter.

One JSON object per line, carrying a fixed base set of keys — ``timestamp``,
``level``, ``logger``, ``message``, ``request_id``, ``service``, ``client_ip`` —
plus whatever whitelisted fields the call site passed (``shared.logging.schema``).

``client_ip`` rides the same per-request contextvar as ``request_id``
(``shared.logging.context``), so it lands on *every* line of a request, not only
the access-log line. It is a base key rather than a schema field for that
reason: a schema field only appears on lines that pass it explicitly, and the
point here is that a call site does not have to.

Timestamps are UTC with millisecond precision, e.g. ``2026-09-10T12:34:56.123Z``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .context import get_client_ip, get_request_id
from .service import SERVICE

_BASE_KEYS = (
    "timestamp",
    "level",
    "logger",
    "message",
    "request_id",
    "service",
    "client_ip",
)


class JSONFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{int(record.msecs):03d}Z"

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
            # Which process wrote this — api / realtime / cli. Without it a
            # pooled stream cannot say whether a line came from the socket
            # process or the API one. See shared.logging.service.
            "service": SERVICE,
            # None outside a request context (a manage.py command's own lines).
            "client_ip": get_client_ip(),
        }

        fields: dict[str, object] = getattr(record, "json_fields", None) or {}
        for key, value in fields.items():
            if key not in _BASE_KEYS:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)
