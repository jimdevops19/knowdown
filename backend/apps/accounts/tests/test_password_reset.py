"""Forgot password: the request half must say nothing, the confirm half must
say everything."""

from __future__ import annotations

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import request_password_reset, reset_password
from apps.core_common.exceptions import ValidationFailed

from .factories import PASSWORD, make_user

NEW_PASSWORD = "another-good-42"


class RequestTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(email="veteran@example.com")
        mail.outbox.clear()

    def _ask(self, email):
        return self.client.post(
            "/api/v1/auth/password/reset/", {"email": email}, format="json"
        )

    def test_a_known_address_gets_a_link(self):
        response = self._ask("veteran@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/reset-password?uid=", mail.outbox[0].body)

    def test_an_unknown_address_is_answered_identically(self):
        """The one endpoint that could otherwise be walked with a mailing list."""
        known = self._ask("veteran@example.com")
        mail.outbox.clear()
        unknown = self._ask("nobody@example.com")

        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json(), unknown.json())
        self.assertEqual(mail.outbox, [])

    def test_an_account_that_cannot_use_a_password_gets_nothing(self):
        """A Google-only account holds an unusable password; a link that reset
        it would create a door that was never offered."""
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.assertEqual(self._ask("veteran@example.com").status_code, 200)
        self.assertEqual(mail.outbox, [])

    def test_an_inactive_account_gets_nothing(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        request_password_reset(email="veteran@example.com")
        self.assertEqual(mail.outbox, [])

    @override_settings(FRONTEND_URL="https://play.knowdown.app/")
    def test_the_link_points_at_the_configured_client(self):
        """Built from a setting, never from the request: which Host reached the
        API says nothing about which UI can complete a token."""
        self._ask("veteran@example.com")
        self.assertIn("https://play.knowdown.app/reset-password?", mail.outbox[0].body)


class ConfirmTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(email="veteran@example.com")

    def _credentials(self, user=None):
        user = user or self.user
        return {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }

    def _service_credentials(self, user=None):
        """The same link, spelled the way the service takes it."""
        payload = self._credentials(user)
        return {"uidb64": payload["uid"], "token": payload["token"]}

    def test_a_good_link_sets_the_password(self):
        response = self.client.post(
            "/api/v1/auth/password/reset/confirm/",
            {**self._credentials(), "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_a_link_works_once(self):
        """The token folds in the password hash, so setting a password spends
        every link outstanding against the account."""
        credentials = self._service_credentials()
        reset_password(**credentials, new_password=NEW_PASSWORD)
        with self.assertRaises(ValidationFailed) as refusal:
            reset_password(**credentials, new_password="third-one-77")
        self.assertEqual(refusal.exception.code, "invalid_reset_token")

    def test_a_forged_link_is_refused(self):
        for uid, token in (
            ("not-base64", "made-up"),
            (urlsafe_base64_encode(force_bytes(self.user.pk)), "made-up"),
        ):
            with self.subTest(uid=uid):
                with self.assertRaises(ValidationFailed):
                    reset_password(uidb64=uid, token=token, new_password=NEW_PASSWORD)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_a_weak_new_password_is_refused(self):
        with self.assertRaises(ValidationFailed) as refusal:
            reset_password(**self._service_credentials(), new_password="password")
        self.assertEqual(refusal.exception.code, "invalid_password")
