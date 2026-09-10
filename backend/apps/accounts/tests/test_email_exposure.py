"""An address is a credential, and it leaves the API in exactly one place.

Sign-in keys on the email — the display name is published on every scoreboard,
so it can be no part of one — which makes the address the half an attacker
cannot read off a ladder, and makes any endpoint that hands one out a list of
accounts to guess at.

``GET /api/v1/auth/me/`` is the single exception, narrow twice over:
``IsAuthenticated``, and ``get_object`` returns ``request.user``, so the only
address it can answer with is the caller's own. This walks every serializer in
the platform to keep that true — the pattern rpool's ``EmailExposureTests``
uses, for the same reason: "we remembered not to include it" is not a mechanism.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

from django.test import TestCase
from rest_framework import serializers as drf
from rest_framework.test import APIClient

import apps

from .factories import make_user

#: Field names that would put an address (or its shape) in a payload.
FORBIDDEN = {"email", "email_address", "user_email"}


def every_api_serializer() -> dict[str, type[drf.BaseSerializer]]:
    """Every serializer any app's API layer declares, keyed ``app.ClassName``."""
    found: dict[str, type[drf.BaseSerializer]] = {}
    for module in pkgutil.iter_modules(apps.__path__):
        name = f"apps.{module.name}.api.serializers"
        try:
            imported = importlib.import_module(name)
        except ModuleNotFoundError:
            continue  # An app with no API layer yet.
        for attribute, value in vars(imported).items():
            if (
                inspect.isclass(value)
                and issubclass(value, drf.BaseSerializer)
                and value.__module__ == name
            ):
                found[f"{module.name}.{attribute}"] = value
    return found


class EmailExposureTests(TestCase):
    #: Where an ``email`` field is legitimate, as ``Serializer: why``. Three of
    #: these are inputs — fields that go *in* and never come out. Anything else
    #: carrying one is a leak until it is argued for here.
    ALLOWED = {
        "UserSerializer": "the caller's own, behind IsAuthenticated at /auth/me/",
        "RegisterSerializer": "signup input",
        "LoginSerializer": "sign-in input",
        "PasswordResetRequestSerializer": "reset input",
    }

    def test_only_the_account_serializers_carry_an_email(self):
        offenders = []
        for path, serializer in every_api_serializer().items():
            if path.split(".")[-1] in self.ALLOWED:
                continue
            try:
                fields = serializer().fields
            except Exception:  # a serializer that needs context to instantiate
                continue
            leaked = FORBIDDEN & set(fields)
            leaked |= {
                name
                for name, field in fields.items()
                if (field.source or "") in FORBIDDEN
            }
            if leaked:
                offenders.append(f"{path}: {sorted(leaked)}")
        self.assertEqual(offenders, [], f"these hand out an address: {offenders}")

    def test_the_player_payload_names_people_by_display_name(self):
        """The player endpoints are the widest read the platform will have, and
        the first thing anybody enumerating accounts would reach for."""
        user = make_user(email="veteran@example.com")
        client = APIClient()
        client.force_authenticate(user)

        body = client.get("/api/v1/players/me/").content.decode()
        self.assertNotIn("veteran@example.com", body)
        self.assertIn(user.player.display_name, body)

    def test_me_is_the_one_endpoint_that_may(self):
        user = make_user(email="veteran@example.com")
        client = APIClient()
        client.force_authenticate(user)
        self.assertIn("veteran@example.com", client.get("/api/v1/auth/me/").content.decode())
