"""``GET /rankings/{category}/`` — step 19's ladder: public, best rating
first, paginated by default."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.matches.tests.factories import make_matchup
from apps.rankings.services import ensure_ranking


class LadderTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_anonymous_can_read_the_ladder(self):
        matchup = make_matchup()
        alice, bob = (side.player for side in matchup.players.all())
        ensure_ranking(player=alice, category=matchup.category)
        ensure_ranking(player=bob, category=matchup.category)

        response = self.client.get(f"/api/v1/rankings/{matchup.category.slug}/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 2)
        self.assertIn("pagination", body["meta"])

    def test_ordered_best_rating_first(self):
        matchup = make_matchup()
        alice, bob = (side.player for side in matchup.players.all())
        from apps.rankings.models import Ranking

        Ranking.objects.filter(
            pk=ensure_ranking(player=alice, category=matchup.category).pk
        ).update(rating=1100)
        Ranking.objects.filter(
            pk=ensure_ranking(player=bob, category=matchup.category).pk
        ).update(rating=1500)

        data = self.client.get(f"/api/v1/rankings/{matchup.category.slug}/").json()["data"]
        self.assertEqual([row["rating"] for row in data], [1500, 1100])
        self.assertEqual(data[0]["player"]["display_name"], bob.display_name)

    def test_an_unknown_category_is_a_404(self):
        response = self.client.get("/api/v1/rankings/does-not-exist/")
        self.assertEqual(response.status_code, 404)

    def test_is_paginated_by_default(self):
        matchup = make_matchup()
        for side in matchup.players.all():
            ensure_ranking(player=side.player, category=matchup.category)

        response = self.client.get(f"/api/v1/rankings/{matchup.category.slug}/")
        pagination = response.json()["meta"]["pagination"]
        self.assertEqual(pagination["page_size"], 25)
        self.assertEqual(pagination["page"], 1)
