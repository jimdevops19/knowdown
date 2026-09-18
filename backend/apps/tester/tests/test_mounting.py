"""The first gate: with ``TESTER_ENDPOINT_ENABLED`` off, these URLs do not exist.

The rest of the suite runs with the flag **on** (``config.settings.test``),
because testing an unmounted route is testing the URLconf rather than the view.
This file is the other half of that bargain, and it is the one that actually
covers the production posture: production sets nothing, so what production runs
is the branch every other test skips.

``config/urls.py`` reads the flag at **import**, which is what makes an
``@override_settings`` alone useless here — the decision was taken before the
test started. So the URLconf is reloaded under the overridden setting and
reloaded back afterwards. That is a heavier hammer than a test usually reaches
for, and it is the right one: the alternative is a fixture URLconf that mounts
the tester unconditionally, which would prove that `include()` works and
nothing about the line that decides whether it is called.
"""

from __future__ import annotations

import importlib

from django.test import override_settings
from django.urls import NoReverseMatch, clear_url_caches, reverse
from rest_framework.test import APITestCase

import config.urls

from apps.questions.tests.factories import make_single_answer
from apps.tester.tests.test_api import client_for, make_maintainer


def _reload_urlconf() -> None:
    """Rebuild the root URLconf against the settings in force right now.

    Both caches have to go: ``clear_url_caches`` drops the resolver Django
    memoises per URLconf, and the reload re-runs the module-level ``if``. Called
    once to take the flag away and once to put it back — a leaked unmounted
    URLconf would fail every other test in the run, in a way that points at
    whichever test happened to run next.
    """
    clear_url_caches()
    importlib.reload(config.urls)
    clear_url_caches()


class MountingTests(APITestCase):
    def tearDown(self):
        _reload_urlconf()
        super().tearDown()

    def test_the_routes_are_mounted_when_the_flag_is_on(self):
        """The control. Without it, a typo in the path would make the test
        below pass for the wrong reason, forever."""
        self.assertEqual(reverse("v1:tester:config"), "/api/v1/tester/config/")

    def test_the_flag_off_leaves_nothing_to_authenticate_against(self):
        question = make_single_answer(slug="unmounted")
        staff = make_maintainer()

        with override_settings(TESTER_ENDPOINT_ENABLED=False):
            _reload_urlconf()
            client = client_for(staff)

            for path in (
                "/api/v1/tester/config/",
                "/api/v1/tester/questions/",
                f"/api/v1/tester/questions/single-answer/{question.id}/",
                f"/api/v1/tester/questions/single-answer/{question.id}/answer-key/",
            ):
                with self.subTest(path=path):
                    # 404, not 403: a staff account is turned away by the
                    # *router*, which is a stronger statement than a permission
                    # refusing them. There is no view here to get wrong.
                    self.assertEqual(client.get(path).status_code, 404)

            self.assertEqual(
                client.post(
                    f"/api/v1/tester/questions/single-answer/{question.id}/answer/",
                    {"submitted": {"type": "single-answer", "option_id": 1}},
                    format="json",
                ).status_code,
                404,
            )

            with self.assertRaises(NoReverseMatch):
                reverse("v1:tester:config")

    def test_the_permission_refuses_even_a_staff_account_while_the_flag_is_off(self):
        """The second gate does not lean on the first.

        Reached here through a URLconf that still has the routes mounted, with
        the flag switched off underneath it — which is exactly the state a
        second mount, or a stale resolver, would produce. ``IsMaintainer``
        re-reads the setting for this case and nothing else.
        """
        question = make_single_answer(slug="belt-and-braces")
        client = client_for(make_maintainer())

        with override_settings(TESTER_ENDPOINT_ENABLED=False):
            response = client.get(
                f"/api/v1/tester/questions/single-answer/{question.id}/"
            )

        self.assertEqual(response.status_code, 403)
