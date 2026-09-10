"""The doors, over HTTP: signing up, signing in, and who may see an address."""

from __future__ import annotations

from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.players.models import Player

from .factories import PASSWORD, make_user

REFRESH_COOKIE = settings.REST_AUTH["JWT_AUTH_REFRESH_COOKIE"]


class RegisterEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_signing_up_answers_with_a_usable_access_token(self):
        response = self.client.post(
            "/api/v1/auth/registration/",
            {
                "email": "rookie@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("access", response.json()["data"])
        self.assertEqual(Player.objects.count(), 1)

    def test_the_refresh_token_never_reaches_the_body(self):
        """It is a week-long credential; a script on the page must not be able
        to read it. The cookie is HttpOnly and scoped to the auth routes."""
        response = self.client.post(
            "/api/v1/auth/registration/",
            {"email": "rookie@example.com", "password1": PASSWORD, "password2": PASSWORD},
            format="json",
        )
        self.assertNotIn("refresh", response.json()["data"])
        cookie = response.cookies[REFRESH_COOKIE]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["path"], "/api/v1/auth/")

    def test_mismatched_passwords_are_refused(self):
        response = self.client.post(
            "/api/v1/auth/registration/",
            {"email": "rookie@example.com", "password1": PASSWORD, "password2": "other-one-17"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 0)


class LoginEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(email="veteran@example.com")

    def _sign_in(self, **payload):
        return self.client.post("/api/v1/auth/token/", payload, format="json")

    def test_the_right_password_answers_with_tokens(self):
        response = self._sign_in(email="veteran@example.com", password=PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json()["data"])
        self.assertNotIn("refresh", response.json()["data"])

    def test_the_address_is_matched_case_insensitively(self):
        response = self._sign_in(email="VETERAN@example.com", password=PASSWORD)
        self.assertEqual(response.status_code, 200)

    def test_sign_in_is_not_an_account_existence_oracle(self):
        """A wrong password, an unknown address and a malformed one are refused
        identically. Any difference between them is a way to sort a list of
        addresses into "has an account" and "doesn't"."""
        refusals = [
            self._sign_in(email="veteran@example.com", password="wrong-one-99"),
            self._sign_in(email="nobody@example.com", password="wrong-one-99"),
            self._sign_in(email="not-an-address", password="wrong-one-99"),
        ]
        bodies = {r.json()["error"]["message"] for r in refusals}
        codes = {r.json()["error"]["code"] for r in refusals}
        statuses = {r.status_code for r in refusals}

        self.assertEqual(len(bodies), 1, bodies)
        self.assertEqual(len(codes), 1, codes)
        self.assertEqual(statuses, {401})

    def test_an_inactive_account_is_refused_the_same_way(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        response = self._sign_in(email="veteran@example.com", password=PASSWORD)
        self.assertEqual(response.status_code, 401)


class MeEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(email="veteran@example.com")
        self.client.force_authenticate(self.user)

    def test_it_answers_with_the_callers_own_account(self):
        payload = self.client.get("/api/v1/auth/me/").json()["data"]
        self.assertEqual(payload["email"], "veteran@example.com")
        self.assertEqual(payload["player_name"], self.user.player.display_name)
        self.assertTrue(payload["player_name_is_auto"])

    def test_an_address_can_be_corrected_here(self):
        response = self.client.patch(
            "/api/v1/auth/me/", {"email": "new@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")

    def test_anonymous_callers_are_refused(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)


class AuthConfigTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_it_says_which_doors_exist(self):
        payload = self.client.get("/api/v1/auth/config/").json()["data"]
        self.assertEqual(
            payload, {"password_enabled": True, "google_enabled": settings.GOOGLE_OAUTH_ENABLED}
        )

    def test_it_is_readable_before_anybody_has_signed_in(self):
        """It is what the sign-in screen asks in order to draw itself."""
        self.assertEqual(self.client.get("/api/v1/auth/config/").status_code, 200)


class TokenLifecycleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        make_user(email="veteran@example.com")

    def test_a_refresh_rotates_the_cookie_without_a_body_token(self):
        self.client.post(
            "/api/v1/auth/token/",
            {"email": "veteran@example.com", "password": PASSWORD},
            format="json",
        )
        response = self.client.post("/api/v1/auth/token/refresh/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json()["data"])
        self.assertIn(REFRESH_COOKIE, response.cookies)

    def test_a_refresh_with_no_cookie_is_refused_rather_than_crashing(self):
        response = self.client.post("/api/v1/auth/token/refresh/", {}, format="json")
        self.assertIn(response.status_code, (400, 401))
