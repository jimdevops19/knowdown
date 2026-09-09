"""Domain exceptions and the DRF exception handler.

Services and validators raise :class:`DomainError` subclasses; they know nothing
about HTTP. The handler is the single place where any exception — domain, DRF or
Django — is turned into the consistent error envelope::

    {"error": {"code": "...", "message": "...", "details": {...}, "request_id": "..."}}
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status as http_status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

from shared.logging import get_logger, get_request_id

logger = get_logger(__name__)


class DomainError(Exception):
    """Base class for expected, business-rule failures.

    ``status_code`` and ``code`` map to the HTTP response; ``details`` carries
    structured, machine-readable context (e.g. per-field errors, or the list of
    problems in a resource file).
    """

    status_code: int = http_status.HTTP_400_BAD_REQUEST
    code: str = "domain_error"
    message: str = "The request could not be completed."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Any = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details
        if code:
            self.code = code
        super().__init__(self.message)


class ValidationFailed(DomainError):
    status_code = http_status.HTTP_400_BAD_REQUEST
    code = "validation_failed"
    message = "Validation failed."


class NotFound(DomainError):
    status_code = http_status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Resource not found."


class PermissionDenied(DomainError):
    status_code = http_status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "You do not have permission to perform this action."


class Conflict(DomainError):
    """State conflict — e.g. answering the same question twice."""

    status_code = http_status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The request conflicts with the current state of the resource."


def _envelope(
    code: str,
    message: str,
    details: Any,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> Response:
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": get_request_id(),
            }
        },
        status=status_code,
        headers=headers,
    )


def _translate_django_exception(exc: Exception) -> Exception:
    """Map Django-native exceptions to their ``DomainError`` equivalents, so
    services and validators may raise either flavour and still land in the same
    envelope."""
    if isinstance(exc, DjangoValidationError):
        return ValidationFailed(details=getattr(exc, "message_dict", exc.messages))
    if isinstance(exc, Http404):
        return NotFound()
    if isinstance(exc, DjangoPermissionDenied):
        return PermissionDenied()
    return exc


def _envelope_fields_from_drf_response(data: Any) -> tuple[str, str, Any]:
    """Derive ``(code, message, details)`` from a DRF default-handler body."""
    if isinstance(data, dict) and "detail" in data:
        message = str(data["detail"])
        code = getattr(data["detail"], "code", None) or "error"
        return code, message, None
    # Serializer errors: {field: [msgs]} — keep as structured details.
    return "validation_failed", "Validation failed.", data


def _called(context: dict) -> tuple[str | None, str | None]:
    """The ``(method, path)`` of the request being handled.

    A failure line naming only its error code ("Domain error: not_found") is the
    same line for every endpoint in the platform; naming the call is what makes
    it possible to see *what someone was trying to do* without joining the line
    back to the access log by request id. ``(None, None)`` when the handler was
    reached without a request.
    """
    request = context.get("request")
    return getattr(request, "method", None), getattr(request, "path", None)


def drf_exception_handler(exc: Exception, context: dict) -> Response | None:
    """DRF ``EXCEPTION_HANDLER``. Normalises every error into the envelope."""
    exc = _translate_django_exception(exc)
    method, path = _called(context)
    called = f"{method or '?'} {path or '?'}"

    if isinstance(exc, DomainError):
        log = logger.warning if isinstance(exc, PermissionDenied) else logger.info
        log(
            f"{called} refused — {exc.code}: {exc.message}",
            code=exc.code,
            reason=exc.message,
            method=method,
            path=path,
        )
        return _envelope(exc.code, exc.message, exc.details, exc.status_code)

    # Fall back to DRF's handler for APIException & co, then re-wrap the body.
    response = drf_default_handler(exc, context)
    if response is None:
        # Not a DomainError and not something DRF recognises — an unexpected,
        # server-side failure. This is the one place every such exception funnels
        # through, so it is the safety net for 500s.
        logger.exception(
            f"{called} crashed — unhandled exception, the caller got a 500",
            method=method,
            path=path,
        )
        return None

    code, message, details = _envelope_fields_from_drf_response(response.data)
    # Carry DRF's own headers across. The body is rebuilt here, so anything the
    # default handler put beside it would otherwise be dropped — and one of those
    # is `Retry-After` on a 429, the only part of a throttle that tells the
    # caller when to come back.
    return _envelope(
        code, message, details, response.status_code, headers=dict(response.headers)
    )
