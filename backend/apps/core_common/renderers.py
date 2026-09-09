"""Success-response envelope.

Every successful JSON body is wrapped as ``{"data": ...}`` (paginated responses
add a sibling ``"meta"`` — see :mod:`apps.core_common.pagination`). Error bodies
are produced already-shaped by the exception handler and pass through untouched.
"""

from __future__ import annotations

from typing import Any

from rest_framework.renderers import JSONRenderer


class EnvelopeJSONRenderer(JSONRenderer):
    def render(self, data: Any, accepted_media_type=None, renderer_context=None) -> bytes:
        renderer_context = renderer_context or {}
        response = renderer_context.get("response")
        status_code = getattr(response, "status_code", 200)

        if status_code >= 400:
            payload = data  # already an {"error": ...} envelope
        elif isinstance(data, dict) and data.keys() <= {"data", "meta"} and "data" in data:
            payload = data  # already enveloped (e.g. by the paginator)
        else:
            payload = {"data": data}

        return super().render(payload, accepted_media_type, renderer_context)
