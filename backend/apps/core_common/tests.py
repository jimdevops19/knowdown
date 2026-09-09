"""Tests for the platform-wide contracts every app inherits."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient


class HealthProbeTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def test_liveness_is_open_and_process_only(self) -> None:
        response = self.client.get("/api/v1/health/live/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"data": {"status": "ok"}})

    def test_readiness_reports_the_database(self) -> None:
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"data": {"status": "ok", "database": True}}
        )


class EnvelopeTests(TestCase):
    """Every body leaves through the envelope — success under ``data``, failure
    under ``error`` with the request id that produced it."""

    def setUp(self) -> None:
        self.client = APIClient()

    def test_success_is_wrapped_in_data(self) -> None:
        payload = self.client.get("/api/v1/health/live/").json()
        self.assertIn("data", payload)

    def test_error_carries_code_and_request_id(self) -> None:
        response = self.client.get("/api/v1/categories/no-such-category/")
        self.assertEqual(response.status_code, 404)
        error = response.json()["error"]
        self.assertEqual(error["code"], "not_found")
        self.assertTrue(error["request_id"])

    def test_request_id_is_echoed_and_honoured(self) -> None:
        response = self.client.get(
            "/api/v1/health/live/", headers={"X-Request-ID": "abc123"}
        )
        self.assertEqual(response.headers["X-Request-ID"], "abc123")
