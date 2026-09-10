"""The published name: its shape, and who may hold it."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core_common.exceptions import Conflict, ValidationFailed
from apps.players.models import Player
from apps.players.services import ensure_player_for_user, generate_display_name, set_display_name

from .factories import make_player


class ShapeTests(TestCase):
    def setUp(self):
        self.player = make_player()

    def test_a_reasonable_name_is_accepted(self):
        for name in ("Kobe", "kobe_24", "Bill Russell", "a_b_c"):
            with self.subTest(name=name):
                set_display_name(player=self.player, display_name=name)
                self.assertEqual(self.player.display_name, name)

    def test_a_chosen_name_stops_the_client_asking(self):
        set_display_name(player=self.player, display_name="Kobe")
        self.player.refresh_from_db()
        self.assertFalse(self.player.has_auto_name)

    def test_the_shapes_that_are_refused(self):
        for name in ("ab", "x" * 31, "Kobe  Bryant", "kobe!", "🏀🏀🏀", "", "Kobe\tBryant"):
            with self.subTest(name=name):
                with self.assertRaises(ValidationFailed) as refusal:
                    set_display_name(player=self.player, display_name=name)
                self.assertEqual(refusal.exception.code, "invalid_display_name")

    def test_stray_typing_whitespace_is_trimmed_rather_than_refused(self):
        """Leading and trailing spaces are how a name arrives from a form, not
        a decision anybody made; two names that differ only by them would also
        be indistinguishable on screen."""
        set_display_name(player=self.player, display_name="  Kobe  ")
        self.assertEqual(self.player.display_name, "Kobe")

    def test_names_that_would_read_as_the_platform_are_reserved(self):
        for name in ("admin", "ADMIN", "Knowdown", "xadmin_1", "support", "moderator"):
            with self.subTest(name=name):
                with self.assertRaises(ValidationFailed) as refusal:
                    set_display_name(player=self.player, display_name=name)
                self.assertEqual(refusal.exception.code, "reserved_display_name")


class UniquenessTests(TestCase):
    def setUp(self):
        self.mine = make_player(email="mine@example.com")
        self.theirs = make_player(email="theirs@example.com", display_name="Kobe")

    def test_somebody_elses_name_is_refused_whatever_its_case(self):
        for name in ("Kobe", "kobe", "KOBE"):
            with self.subTest(name=name):
                with self.assertRaises(ValidationFailed) as refusal:
                    set_display_name(player=self.mine, display_name=name)
                self.assertEqual(refusal.exception.code, "display_name_taken")

    def test_recapitalising_my_own_name_is_a_rename_and_not_a_conflict(self):
        set_display_name(player=self.theirs, display_name="KOBE")
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.display_name, "KOBE")

    def test_the_database_enforces_it_too(self):
        """The validator reads before the write, so two claims landing together
        both pass it. The constraint is what settles the race — which is why it
        exists as well as the validator, and not instead of it."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Player.objects.create(display_name="kobe")

    def test_a_lost_race_is_a_conflict_and_not_a_500(self):
        Player.objects.filter(pk=self.theirs.pk).update(display_name="Shaq")
        # `self.theirs` is stale in memory; the row now holds "Shaq", so the
        # validator sees "Kobe" free while another row is about to take it.
        Player.objects.filter(pk=self.mine.pk).update(display_name="Kobe")
        stale = Player.objects.get(pk=self.theirs.pk)
        stale.display_name = "Shaq"
        with self.assertRaises((Conflict, ValidationFailed)):
            set_display_name(player=stale, display_name="Kobe")


class GeneratedNameTests(TestCase):
    def test_a_new_player_gets_a_temporary_name(self):
        player = make_player()
        self.assertTrue(player.has_auto_name)
        self.assertTrue(player.display_name.startswith("player_"))

    def test_a_generated_name_is_free_when_it_is_handed_out(self):
        taken = {make_player(email=f"p{i}@example.com").display_name for i in range(5)}
        self.assertEqual(len(taken), 5)
        self.assertNotIn(generate_display_name(), taken)

    def test_asking_twice_gives_the_same_player(self):
        """Every path that can make an account calls this, so it has to be
        idempotent — an account with two competitors has two match histories."""
        player = make_player()
        self.assertEqual(ensure_player_for_user(user=player.user), player)
        self.assertEqual(Player.objects.count(), 1)
