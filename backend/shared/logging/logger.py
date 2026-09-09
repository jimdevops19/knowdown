"""The logger every app should use instead of ``logging.getLogger`` directly.

    from shared.logging import get_logger, labels

    logger = get_logger(__name__)
    logger.info("Questions synced", category=labels.category(category), summary=str(report))

Custom fields are passed as keywords rather than the stdlib's ``extra={...}``
dict; each keyword is checked against ``shared.logging.schema.SUPPORTED_LOG_FIELDS``
so every log line stays on the shared JSON schema instead of each call site
inventing its own key for the same concept.

Entities go in as the label ``shared.logging.labels`` builds for them, never as
a raw id — see that module and ``schema.py`` on why the logs name things rather
than number them.
"""

from __future__ import annotations

import logging

from .schema import SUPPORTED_LOG_FIELDS, UnsupportedLogFieldError

# Custom level for actions attempted but not permitted (e.g. answering a
# question in a matchup you are not in). Between WARNING (30) and ERROR (40):
# not a bug, but louder than a normal warning, and countable on its own.
VIOLATE_LEVEL = 35
logging.addLevelName(VIOLATE_LEVEL, "VIOLATE")


class JSONLogger:
    """Thin wrapper around :class:`logging.Logger` enforcing the field schema."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _log(self, level: int, message: str, fields: dict[str, object]) -> None:
        unsupported = set(fields) - SUPPORTED_LOG_FIELDS
        if unsupported:
            raise UnsupportedLogFieldError(unsupported)
        self._logger.log(level, message, extra={"json_fields": fields})

    def debug(self, message: str, **fields: object) -> None:
        self._log(logging.DEBUG, message, fields)

    def info(self, message: str, **fields: object) -> None:
        self._log(logging.INFO, message, fields)

    def warning(self, message: str, **fields: object) -> None:
        self._log(logging.WARNING, message, fields)

    def error(self, message: str, **fields: object) -> None:
        self._log(logging.ERROR, message, fields)

    def critical(self, message: str, **fields: object) -> None:
        self._log(logging.CRITICAL, message, fields)

    def violate(self, message: str, **fields: object) -> None:
        """Log a not-permitted action at the custom ``VIOLATE`` level.

        For attempts the platform refused on authorization grounds. Kept off
        WARNING so ordinary warnings stay separable from "someone tried
        something they may not do", which is a thing worth counting.
        """
        self._log(VIOLATE_LEVEL, message, fields)

    def exception(self, message: str, **fields: object) -> None:
        """Log at ERROR with the current exception's traceback attached."""
        unsupported = set(fields) - SUPPORTED_LOG_FIELDS
        if unsupported:
            raise UnsupportedLogFieldError(unsupported)
        self._logger.error(message, extra={"json_fields": fields}, exc_info=True)


def get_logger(name: str) -> JSONLogger:
    return JSONLogger(name)
