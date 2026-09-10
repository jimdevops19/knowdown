"""``GET /players/{display_name}/`` — step 19's public profile: rating per
category, record, badges, in one round trip."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.achievements.services import sync_achievements
from apps.achievements.tests.factories import play_matchup
from apps.matches.constants import DEFAULT_PLAYER_RATING
from apps.rankings.selectors import get_ranking

from .factories import make_player


class ProfileTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_anonymous_can_read_a_profile(self):
        player = make_player(email="kobe@example.com", display_name="Kobe")
        response = self.client.get(f"/api/v1/players/{player.display_name}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["display_name"], "Kobe")
        self.assertEqual(data["rankings"], [])
        self.assertEqual(data["badges"], [])

    def test_is_looked_up_case_insensitively(self):
        make_player(email="kobe@example.com", display_name="Kobe")
        response = self.client.get("/api/v1/players/kobe/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["display_name"], "Kobe")

    def test_an_unknown_name_is_a_404(self):
        response = self.client.get("/api/v1/players/nobody-here/")
        self.assertEqual(response.status_code, 404)

    def test_carries_no_email_address(self):
        player = make_player(email="kobe@example.com", display_name="Kobe")
        data = self.client.get(f"/api/v1/players/{player.display_name}/").json()["data"]
        self.assertNotIn("email", data)

    def test_shows_a_rating_per_category_and_the_record_behind_it(self):
        sync_achievements()
        alice = make_player(email="alice@example.com", display_name="Alice")
        bob = make_player(email="bob@example.com", display_name="Bob")
        matchup = play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)

        data = self.client.get(f"/api/v1/players/{alice.display_name}/").json()["data"]
        self.assertEqual(len(data["rankings"]), 1)
        row = data["rankings"][0]
        self.assertEqual(row["category"], matchup.category.slug)
        self.assertEqual(row["wins"], 1)
        self.assertEqual(row["losses"], 0)
        self.assertEqual(row["games_played"], 1)
        self.assertGreater(row["rating"], DEFAULT_PLAYER_RATING)

        alice_entry = get_ranking(player=alice, category=matchup.category)
        self.assertEqual(row["rating"], alice_entry.rating)

    def test_shows_earned_badges(self):
        sync_achievements()
        alice = make_player(email="alice@example.com", display_name="Alice")
        bob = make_player(email="bob@example.com", display_name="Bob")
        play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)

        data = self.client.get(f"/api/v1/players/{alice.display_name}/").json()["data"]
        slugs = {badge["slug"] for badge in data["badges"]}
        self.assertIn("first-win", slugs)
