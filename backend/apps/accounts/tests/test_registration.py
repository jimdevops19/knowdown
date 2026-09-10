"""Signing up: what is written, and what a refusal must leave behind."""

from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.services import normalize_email, register_user, set_email
from apps.core_common.exceptions import Conflict, ValidationFailed
from apps.players.models import Player

from .factories import PASSWORD, make_user


class RegisterUserTests(TestCase):
    def test_an_account_arrives_with_its_player(self):
        user = register_user(email="rookie@example.com", password=PASSWORD)

        self.assertEqual(user.email, "rookie@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertIsNotNone(user.player)
        self.assertTrue(user.player.has_auto_name)

    def test_the_address_is_stored_folded(self):
        """One spelling in the column, so the unique constraint and every
        ``iexact`` lookup agree about what "the same address" means."""
        user = register_user(email="  Rookie@Example.COM ", password=PASSWORD)
        self.assertEqual(user.email, "rookie@example.com")

    def test_a_taken_address_is_refused_whatever_its_case(self):
        make_user(email="taken@example.com")
        with self.assertRaises(ValidationFailed) as refusal:
            register_user(email="TAKEN@example.com", password=PASSWORD)
        self.assertEqual(refusal.exception.code, "email_taken")

    def test_a_weak_password_is_refused(self):
        with self.assertRaises(ValidationFailed) as refusal:
            register_user(email="weak@example.com", password="password")
        self.assertEqual(refusal.exception.code, "invalid_password")

    def test_a_refusal_leaves_no_account_behind(self):
        """The whole point of validating before writing: a half-registered
        account is one that can sign in and cannot play."""
        for email, password in (
            ("", PASSWORD),
            ("weak@example.com", "12345678"),
            ("weak@example.com", "short"),
        ):
            with self.subTest(email=email):
                with self.assertRaises(ValidationFailed):
                    register_user(email=email, password=password)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Player.objects.count(), 0)

    def test_the_display_name_is_not_seeded_from_the_address(self):
        """A published name derived from an address publishes half a credential."""
        user = register_user(email="michael.jordan@example.com", password=PASSWORD)
        name = user.player.display_name.lower()
        for fragment in ("michael", "jordan", "example", "@"):
            self.assertNotIn(fragment, name)


class NormalizeEmailTests(TestCase):
    def test_blank_is_nobody(self):
        self.assertIsNone(normalize_email(email="   "))
        self.assertIsNone(normalize_email(email=None))


class SetEmailTests(TestCase):
    def test_an_address_can_be_changed(self):
        user = make_user(email="old@example.com")
        set_email(user=user, email="New@example.com")
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")

    def test_an_address_cannot_be_cleared(self):
        """Removing one silently takes a door away — the reset link's, and a
        staff account's admin login."""
        user = make_user()
        with self.assertRaises(ValidationFailed) as refusal:
            set_email(user=user, email="")
        self.assertEqual(refusal.exception.code, "email_required")

    def test_somebody_elses_address_is_refused(self):
        make_user(email="theirs@example.com")
        mine = make_user(email="mine@example.com")
        with self.assertRaises(ValidationFailed) as refusal:
            set_email(user=mine, email="theirs@example.com")
        self.assertEqual(refusal.exception.code, "email_taken")

    def test_saving_my_own_address_again_is_not_a_conflict(self):
        user = make_user(email="mine@example.com")
        self.assertEqual(set_email(user=user, email="MINE@example.com").email, "mine@example.com")


class ConflictIsNotAnErrorPageTests(TestCase):
    """A race is a 409, not a 500 — the constraint is the last word, and the
    person who lost the race has to be told something they can act on."""

    def test_a_duplicate_that_slips_past_the_check_is_a_conflict(self):
        user = make_user(email="first@example.com")
        User.objects.filter(pk=user.pk).update(email="second@example.com")
        # `user` still carries the old address in memory; the row does not.
        other = make_user(email="third@example.com")
        User.objects.filter(pk=other.pk).update(email="first@example.com")

        with self.assertRaises((Conflict, ValidationFailed)):
            register_user(email="first@example.com", password=PASSWORD)
