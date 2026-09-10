"""What the gate must do, stated as the four answers it can give."""

from __future__ import annotations

import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.ops.models import AdminWindow
from apps.ops.services import any_window_live, close_windows, open_window, window_for_token
from shared.admin_url import OPS_PATH, OPS_STATIC_PATH

GATE = dict(
    ADMIN_GATE_ENABLED=True,
    ADMIN_ENABLED=True,
    ADMIN_URL="admin/",
    ROOT_URLCONF="apps.ops.tests.tests_urls",
    STATIC_URL=OPS_STATIC_PATH,
)


@override_settings(**GATE)
class AdminGateTests(TestCase):
    def setUp(self) -> None:
        self.window, self.token = open_window(minutes=30, opened_by="tests")

    def admin_url(self, token: str) -> str:
        return f"{OPS_PATH}{token}/admin/"

    def test_right_token_reaches_the_admin(self) -> None:
        response = self.client.get(self.admin_url(self.token))
        # Anonymous at the admin index = a redirect to the admin's login page.
        # Reaching *that* is the proof the URL resolved to the admin at all.
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(self.admin_url(self.token)))

    def test_the_redirect_carries_the_token(self) -> None:
        """reverse() must emit token-prefixed URLs, or every link is a 404."""
        response = self.client.get(self.admin_url(self.token))
        self.assertIn(f"{OPS_PATH}{self.token}/admin/login/", response["Location"])

    def test_wrong_token_is_an_ordinary_404(self) -> None:
        response = self.client.get(self.admin_url("not-the-token"))
        self.assertEqual(response.status_code, 404)

    def test_expired_window_is_a_404(self) -> None:
        AdminWindow.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(self.admin_url(self.token)).status_code, 404)

    def test_closed_window_is_a_404(self) -> None:
        close_windows()
        self.assertEqual(self.client.get(self.admin_url(self.token)).status_code, 404)

    def test_the_mounted_prefix_is_not_reachable_directly(self) -> None:
        """Even with a window open — the token is the only way in."""
        self.assertEqual(self.client.get("/admin/").status_code, 404)

    def test_the_token_opens_nothing_but_the_admin(self) -> None:
        response = self.client.get(f"{OPS_PATH}{self.token}/api/v1/health/")
        self.assertEqual(response.status_code, 404)


@override_settings(**GATE, WHITENOISE_AUTOREFRESH=True)
class AdminStaticTests(TestCase):
    """The admin's CSS is gated too — served open, refused closed.

    A real file in a real STATIC_ROOT, because the interesting failure is a
    404 that WhiteNoise would have answered: with nothing on disk both cases
    are 404 and the test proves nothing.
    """

    def setUp(self) -> None:
        self.static_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.static_root, True)
        asset = self.static_root / "admin" / "css" / "base.css"
        asset.parent.mkdir(parents=True)
        asset.write_text("body{}")
        self.asset_url = f"{OPS_STATIC_PATH}admin/css/base.css"
        self.enterContext(override_settings(STATIC_ROOT=str(self.static_root)))
        open_window(minutes=30)

    def test_served_while_a_window_is_open(self) -> None:
        self.assertEqual(self.client.get(self.asset_url).status_code, 200)

    def test_refused_when_no_window_is_open(self) -> None:
        close_windows()
        self.assertEqual(self.client.get(self.asset_url).status_code, 404)


@override_settings(**GATE)
class AdminWindowServiceTests(TestCase):
    def test_opening_supersedes_the_previous_window(self) -> None:
        _, first = open_window(minutes=30)
        _, second = open_window(minutes=30)
        self.assertIsNone(window_for_token(first))
        self.assertIsNotNone(window_for_token(second))

    def test_the_plaintext_token_is_never_stored(self) -> None:
        _, token = open_window(minutes=30)
        self.assertFalse(AdminWindow.objects.filter(token_hash=token).exists())

    def test_any_window_live_follows_the_clock(self) -> None:
        open_window(minutes=30)
        self.assertTrue(any_window_live())
        AdminWindow.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(any_window_live())


class AdminGateOffTests(TestCase):
    """With the gate off nothing changes — the middleware isn't even loaded."""

    @override_settings(ROOT_URLCONF="apps.ops.tests.tests_urls")
    def test_admin_is_reachable_at_its_prefix(self) -> None:
        self.assertEqual(self.client.get("/admin/").status_code, 302)
