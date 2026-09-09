"""Infrastructure endpoints (no domain data)."""

from __future__ import annotations

from django.db import connection
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class _ProbeView(APIView):
    """Shared base for the probes: open, unauthenticated, no domain data."""

    permission_classes = [AllowAny]
    authentication_classes: list = []


class LivenessView(_ProbeView):
    """``GET /api/v1/health/live/`` — **is this process still working?**

    Answers from the process alone and never touches the database. That is the
    whole point of it: a liveness failure gets the container *killed*, so
    anything this probe consults becomes something that can restart every pod in
    the fleet at once. A slow or briefly unreachable Postgres is a partial
    degradation the pods themselves would ride out — checking it here would turn
    it into a restart storm, dropping the pods that were still serving and
    hammering the recovering database with reconnects on the way back up.

    Point ``livenessProbe`` here and ``readinessProbe`` at
    :class:`ReadinessView`, which *does* check the DB — a pod with no database
    should stop receiving traffic (readiness), not be shot (liveness).
    """

    @extend_schema(
        summary="Liveness probe", tags=["infra"], responses=OpenApiTypes.OBJECT
    )
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class ReadinessView(_ProbeView):
    """``GET /api/v1/health/`` — **can this process serve a request right now?**

    Confirms the database is reachable, because a pod that cannot reach it can
    serve nothing worth having; failing here takes the pod out of the Service
    endpoints and back in again by itself once the DB returns, with no restart.
    """

    @extend_schema(
        summary="Readiness probe", tags=["infra"], responses=OpenApiTypes.OBJECT
    )
    def get(self, request: Request) -> Response:
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:  # pragma: no cover - only on a broken DB
            db_ok = False

        payload = {"status": "ok" if db_ok else "degraded", "database": db_ok}
        code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(payload, status=code)
