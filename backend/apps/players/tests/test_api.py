"""``/players/me/`` and the name-availability check, over HTTP."""

from __future__ import annotations

import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.players.models import Player

from .factories import an_image, make_player

MEDIA = tempfile.mkdtemp(prefix="knowdown-avatars-")


class MeTests(TestCase):
    def setUp(self):
        self.player = make_player()
        self.client = APIClient()
        self.client.force_authenticate(self.player.user)

    def test_it_answers_with_the_callers_own_player(self):
        payload = self.client.get("/api/v1/players/me/").json()["data"]
        self.assertEqual(payload["display_name"], self.player.display_name)
        self.assertTrue(payload["has_auto_name"])
        self.assertIsNone(payload["avatar_url"])

    def test_a_name_is_claimed_through_the_service(self):
        response = self.client.patch(
            "/api/v1/players/me/", {"display_name": "Kobe"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.player.refresh_from_db()
        self.assertEqual(self.player.display_name, "Kobe")
        self.assertFalse(self.player.has_auto_name)

    def test_a_refused_name_says_why(self):
        make_player(email="theirs@example.com", display_name="Kobe")
        response = self.client.patch(
            "/api/v1/players/me/", {"display_name": "kobe"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "display_name_taken")

    def test_a_patch_cannot_route_around_the_validator(self):
        """The serializer's field is read-only and the view calls the service,
        so there is no payload shape that writes the column directly."""
        for payload in ({"display_name": "admin"}, {"has_auto_name": False}):
            with self.subTest(payload=payload):
                self.client.patch("/api/v1/players/me/", payload, format="json")
        self.player.refresh_from_db()
        self.assertTrue(self.player.has_auto_name)
        self.assertNotEqual(self.player.display_name, "admin")

    def test_an_account_with_no_player_gets_one_here(self):
        """An account made from the shell has never had a competitor; asking
        for it is a fine moment to make one."""
        from apps.accounts.models import User

        stray = User.objects.create_user(email="shell@example.com", password="correct-horse-19")
        client = APIClient()
        client.force_authenticate(stray)
        self.assertEqual(client.get("/api/v1/players/me/").status_code, 200)
        self.assertTrue(Player.objects.filter(user=stray).exists())

    def test_anonymous_callers_are_refused(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/v1/players/me/").status_code, 401)


@override_settings(MEDIA_ROOT=MEDIA)
class AvatarTests(TestCase):
    def setUp(self):
        self.player = make_player()
        self.client = APIClient()
        self.client.force_authenticate(self.player.user)

    def test_a_picture_can_be_uploaded_and_read_back(self):
        response = self.client.patch(
            "/api/v1/players/me/", {"avatar": an_image()}, format="multipart"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()["data"]["avatar_url"])

    def test_a_file_that_is_not_an_image_is_refused(self):
        """Checked for what it *is*: an extension is a claim the uploader makes."""
        disguised = SimpleUploadedFile("avatar.png", b"not an image", content_type="image/png")
        response = self.client.patch(
            "/api/v1/players/me/", {"avatar": disguised}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_avatar")

    def test_a_picture_can_be_cleared(self):
        self.client.patch("/api/v1/players/me/", {"avatar": an_image()}, format="multipart")
        response = self.client.patch(
            "/api/v1/players/me/", {"avatar": ""}, format="multipart"
        )
        self.assertIsNone(response.json()["data"]["avatar_url"])


class MascotTests(TestCase):
    """Choosing a mark. A key, one of a named set, or nothing at all."""

    def setUp(self):
        self.player = make_player()
        self.client = APIClient()
        self.client.force_authenticate(self.player.user)

    def test_it_starts_with_no_mascot(self):
        self.assertIsNone(self.client.get("/api/v1/players/me/").json()["data"]["mascot"])

    def test_a_mascot_can_be_chosen_and_read_back(self):
        response = self.client.patch(
            "/api/v1/players/me/", {"mascot": "raptor"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["mascot"], "raptor")
        self.player.refresh_from_db()
        self.assertEqual(self.player.mascot, "raptor")

    def test_a_key_nobody_draws_is_refused(self):
        """An allow-list, not a shape check: an unknown key would reach a
        scoreboard as an empty disc."""
        response = self.client.patch(
            "/api/v1/players/me/", {"mascot": "tyrannosaurus"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_mascot")
        self.player.refresh_from_db()
        self.assertEqual(self.player.mascot, "")

    def test_a_mascot_can_be_cleared(self):
        self.client.patch("/api/v1/players/me/", {"mascot": "raptor"}, format="json")
        response = self.client.patch("/api/v1/players/me/", {"mascot": ""}, format="json")
        self.assertIsNone(response.json()["data"]["mascot"])

    def test_a_patch_that_never_mentions_it_leaves_it_alone(self):
        self.client.patch("/api/v1/players/me/", {"mascot": "raptor"}, format="json")
        self.client.patch("/api/v1/players/me/", {"display_name": "Kobe"}, format="json")
        self.player.refresh_from_db()
        self.assertEqual(self.player.mascot, "raptor")

    def test_it_is_published_on_a_public_profile(self):
        """The mark is how somebody is recognised, so it travels wherever the
        name does — not only on the caller's own payload."""
        self.client.patch("/api/v1/players/me/", {"mascot": "hornet"}, format="json")
        payload = self.client.get(
            f"/api/v1/players/{self.player.display_name}/"
        ).json()["data"]
        self.assertEqual(payload["mascot"], "hornet")

    def test_every_key_the_allow_list_names_is_accepted(self):
        from apps.players.constants import MASCOT_KEYS

        self.assertEqual(len(MASCOT_KEYS), 41)
        for key in sorted(MASCOT_KEYS):
            with self.subTest(mascot=key):
                response = self.client.patch(
                    "/api/v1/players/me/", {"mascot": key}, format="json"
                )
                self.assertEqual(response.status_code, 200)

    def test_the_allow_list_is_the_set_the_client_can_draw(self):
        """The mascot list lives in two files — the drawings in
        ``frontend/src/components/avatars/marks.ts`` and the names in
        ``apps.players.constants`` — and nothing but this test stops them
        drifting. A mark added on one side only would be a picker offering an
        option the API answers 400 to, or a stored key nobody draws.

        Read as text rather than imported, obviously: there is no TypeScript
        here. The shape it matches (``key: 'raptor',``) is the one the file is
        written in, and a rewrite that breaks the match fails loudly.
        """
        import re
        from pathlib import Path

        from apps.players.constants import MASCOT_KEYS

        marks = (
            Path(settings.BASE_DIR).parent
            / "frontend/src/components/avatars/marks.ts"
        )
        if not marks.exists():  # a backend-only checkout or container image
            self.skipTest("the client is not in this tree")

        drawn = set(re.findall(r"^\s*key: '([a-z-]+)',$", marks.read_text(), re.M))
        self.assertEqual(drawn, set(MASCOT_KEYS))


class DisplayNameAvailableTests(TestCase):
    def setUp(self):
        self.player = make_player()
        self.client = APIClient()
        self.client.force_authenticate(self.player.user)

    def _ask(self, name):
        return self.client.get(
            "/api/v1/players/display-name-available/", {"display_name": name}
        ).json()["data"]

    def test_a_free_name_is_available(self):
        self.assertTrue(self._ask("Kobe")["available"])

    def test_a_taken_name_says_so_without_naming_anybody(self):
        make_player(email="theirs@example.com", display_name="Kobe")
        answer = self._ask("KOBE")
        self.assertFalse(answer["available"])
        self.assertEqual(answer["reason"], "display_name_taken")
        self.assertNotIn("theirs@example.com", str(answer))

    def test_a_name_of_the_wrong_shape_is_answered_the_same_way(self):
        """One call answers "may I have this?" — being refused for the shape
        and being refused for the owner are the same question to the screen
        asking it."""
        self.assertEqual(self._ask("ab")["reason"], "invalid_display_name")
        self.assertEqual(self._ask("admin")["reason"], "reserved_display_name")

    def test_my_own_name_is_available_to_me(self):
        self.assertTrue(self._ask(self.player.display_name.upper())["available"])

    def test_asking_about_nothing_is_a_refusal(self):
        response = self.client.get("/api/v1/players/display-name-available/")
        self.assertEqual(response.status_code, 400)

    def test_anonymous_callers_are_refused(self):
        """Otherwise it is an anonymous way to sweep which names exist."""
        self.client.force_authenticate(None)
        response = self.client.get(
            "/api/v1/players/display-name-available/", {"display_name": "Kobe"}
        )
        self.assertEqual(response.status_code, 401)
