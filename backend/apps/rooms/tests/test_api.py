"""The lobby endpoints: what a client sees, and what it does not."""

from __future__ import annotations

from django.test import TestCase

from apps.questions.tests.factories import make_category, make_single_answer
from apps.rooms.tests.factories import make_room


class RoomApiTests(TestCase):
    def setUp(self):
        self.nba = make_category()
        make_single_answer(slug="q-1", category=self.nba, level=5)
        self.room = make_room(
            slug="finals-room",
            name="Ring Chasing",
            counts=[4, 5, 6],
            description="June basketball only.",
            categories=[(self.nba, {"topic": "finals"})],
        )

    def test_the_lobby_is_open_to_a_signed_out_visitor(self):
        """What there is to play is the pitch; joining is what needs an
        account, and that gate is on the socket."""
        response = self.client.get("/api/v1/rooms/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["data"]), 1)

    def test_a_room_carries_its_settings(self):
        room = self.client.get("/api/v1/rooms/").json()["data"][0]
        self.assertEqual(room["slug"], "finals-room")
        self.assertEqual(room["name"], "Ring Chasing")
        self.assertEqual(room["question_counts"], [4, 5, 6])
        self.assertEqual(
            room["categories"],
            [{"slug": "nba", "name": "NBA", "filter_tags": {"topic": "finals"}}],
        )

    def test_the_lobby_says_whether_a_room_is_rated(self):
        """The client shows this before a player joins, so it has to arrive
        with the room rather than be inferred from ``categories``."""
        single = self.client.get("/api/v1/rooms/finals-room/").json()["data"]
        self.assertTrue(single["is_rated"])

        f1 = make_category(slug="f1", name="F1")
        mixed = make_room(slug="mixed", categories=[(self.nba, {}), (f1, {})])
        payload = self.client.get(f"/api/v1/rooms/{mixed.slug}/").json()["data"]
        self.assertFalse(payload["is_rated"])

    def test_a_room_never_exposes_its_uuid(self):
        """The slug is the identifier the API takes and answers with; a second
        one invites clients to key on it and break on the next sync."""
        self.assertNotIn("id", self.client.get("/api/v1/rooms/").json()["data"][0])

    def test_the_pool_size_says_whether_the_room_can_be_played(self):
        response = self.client.get("/api/v1/rooms/finals-room/")
        self.assertEqual(response.json()["data"]["question_pool_size"], 0)
        question = make_single_answer(slug="finals-q", category=self.nba, level=5)
        question.tags = {"topic": "finals"}
        question.save(update_fields=["tags"])
        response = self.client.get("/api/v1/rooms/finals-room/")
        self.assertEqual(response.json()["data"]["question_pool_size"], 1)

    def test_an_inactive_room_is_not_in_the_lobby(self):
        make_room(slug="parked", is_active=False, categories=[(self.nba, {})])
        slugs = [r["slug"] for r in self.client.get("/api/v1/rooms/").json()["data"]]
        self.assertNotIn("parked", slugs)
        self.assertEqual(self.client.get("/api/v1/rooms/parked/").status_code, 404)

    def test_an_unknown_room_is_a_404(self):
        self.assertEqual(self.client.get("/api/v1/rooms/nope/").status_code, 404)

    def test_the_lobby_is_read_only(self):
        """Rooms are authored in a pull request, not through an endpoint."""
        self.assertEqual(self.client.post("/api/v1/rooms/", {}).status_code, 405)
