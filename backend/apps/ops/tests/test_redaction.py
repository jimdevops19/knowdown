"""The live token never appears in an access-log line.

`AccessLogMiddleware` (apps.core_common.middleware) writes one line per
request, `path` field included — this proves the field it writes for a gated
request has had `shared.admin_url.redact_ops_path` applied, unit-testing the
helper directly and then over the wire through a real gated request.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.ops.services import open_window
from shared.admin_url import OPS_PATH, OPS_STATIC_PATH, redact_ops_path


class RedactOpsPathTests(TestCase):
    def test_a_token_path_is_redacted(self) -> None:
        self.assertEqual(
            redact_ops_path(f"{OPS_PATH}abc123/admin/login/"),
            f"{OPS_PATH}<token>/admin/login/",
        )

    def test_the_static_path_is_left_alone(self) -> None:
        # No token lives under /_ops/static/ — nothing to redact.
        path = f"{OPS_STATIC_PATH}admin/css/base.css"
        self.assertEqual(redact_ops_path(path), path)

    def test_an_ordinary_path_is_left_alone(self) -> None:
        path = "/api/v1/categories/nba/"
        self.assertEqual(redact_ops_path(path), path)

    def test_the_bare_prefix_is_left_alone(self) -> None:
        self.assertEqual(redact_ops_path(OPS_PATH), OPS_PATH)


@override_settings(
    ADMIN_GATE_ENABLED=True,
    ADMIN_ENABLED=True,
    ADMIN_URL="admin/",
    ROOT_URLCONF="apps.ops.tests.tests_urls",
)
class AccessLogRedactionTests(TestCase):
    """The access log line itself, not just the helper underneath it."""

    def test_the_token_does_not_reach_the_log_line(self) -> None:
        _, token = open_window(minutes=30)
        with self.assertLogs("apps.core_common.middleware", level="INFO") as captured:
            self.client.get(f"{OPS_PATH}{token}/admin/login/")
        joined = "\n".join(captured.output)
        self.assertNotIn(token, joined)
        self.assertIn(f"{OPS_PATH}<token>/admin/login/", joined)
