"""Google sign-in on a deployment that has no Google credentials.

Which is every deployment until somebody registers an OAuth app, so this is the
state the code has to be *correct* in rather than merely tolerant of: an
unconfigured provider must say so, and must not be registered with empty
strings and left to fail somewhere deep inside allauth.
"""

from __future__ import annotations

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.adapters import SocialAccountAdapter
from apps.accounts.models import User
from apps.core_common.exceptions import ValidationFailed

from .factories import make_user


class UnconfiguredGoogleTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_no_credentials_means_no_registered_app(self):
        """Left *unconfigured*, not configured with blanks. A provider with an
        empty client id is one that fails at token exchange with an opaque
        error; one with no app at all is one this API can talk about."""
        if settings.GOOGLE_OAUTH_ENABLED:
            self.skipTest("This environment has Google credentials configured.")
        self.assertNotIn("APP", settings.SOCIALACCOUNT_PROVIDERS["google"])

    def test_the_config_endpoint_says_so(self):
        payload = self.client.get("/api/v1/auth/config/").json()["data"]
        self.assertEqual(payload["google_enabled"], settings.GOOGLE_OAUTH_ENABLED)

    def test_signing_in_with_google_is_refused_in_words(self):
        if settings.GOOGLE_OAUTH_ENABLED:
            self.skipTest("This environment has Google credentials configured.")
        response = self.client.post(
            "/api/v1/auth/google/", {"access_token": "whatever"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"], "google_oauth_not_configured"
        )


#: The adapter's rules only come into play on a tier that *has* Google
#: configured, so its tests ask for that state rather than testing the adapter
#: against a provider that could never be reached.
GOOGLE_CONFIGURED = override_settings(
    GOOGLE_OAUTH_ENABLED=True,
    SOCIALACCOUNT_PROVIDERS={
        "google": {
            "SCOPE": ["profile", "email"],
            "AUTH_PARAMS": {"access_type": "online"},
            "APP": {"client_id": "test-client-id", "secret": "test-secret", "key": ""},
        }
    },
)


@GOOGLE_CONFIGURED
class AdapterTests(TestCase):
    """The adapter's rules, exercised without an OAuth round trip.

    Both of these are cases where allauth would otherwise decline to
    auto-create the account and redirect to its own signup form — a page this
    JSON API does not route, so the fallback is a 500 on the sign-in endpoint
    for what is really "we can't sign you in like this".
    """

    def setUp(self):
        from allauth.socialaccount.adapter import get_adapter

        self.adapter = get_adapter()
        self.request = RequestFactory().post("/api/v1/auth/google/")

    def _social_login(self, *, email: str | None, verified: bool = True):
        user = User(email=email or "")
        account = SocialAccount(provider="google", uid="google-uid-1")
        addresses = (
            [EmailAddress(email=email, verified=verified)] if email else []
        )
        return SocialLogin(user=user, account=account, email_addresses=addresses)

    def test_the_adapter_in_use_is_ours(self):
        self.assertIsInstance(self.adapter, SocialAccountAdapter)

    def test_google_without_an_email_is_refused_in_words(self):
        """The consent screen lets somebody untick the email permission; the
        message has to name the checkbox they need to tick."""
        with self.assertRaises(ValidationFailed) as refusal:
            self.adapter.pre_social_login(self.request, self._social_login(email=None))
        self.assertEqual(refusal.exception.code, "google_email_permission_required")

    def test_a_verified_address_links_to_the_account_that_holds_it(self):
        """Typically an account made before Google sign-in existed. Google has
        verified the address, so its owner is the person in front of us —
        linking beats locking them out of their own account."""
        existing = make_user(email="veteran@example.com")

        self.adapter.pre_social_login(
            self.request, self._social_login(email="Veteran@example.com")
        )

        self.assertTrue(
            SocialAccount.objects.filter(user=existing, provider="google").exists()
        )

    def test_an_unverified_address_does_not(self):
        """An unverified address is a claim, and honouring it would let anyone
        type their way into somebody else's account."""
        make_user(email="veteran@example.com")
        with self.assertRaises(ValidationFailed) as refusal:
            self.adapter.pre_social_login(
                self.request,
                self._social_login(email="veteran@example.com", verified=False),
            )
        self.assertEqual(refusal.exception.code, "email_already_registered")

    def test_an_address_nobody_holds_is_left_to_allauth(self):
        self.assertIsNone(
            self.adapter.pre_social_login(
                self.request, self._social_login(email="newcomer@example.com")
            )
        )
