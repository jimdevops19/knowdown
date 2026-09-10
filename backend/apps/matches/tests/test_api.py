"""Match history over REST: read-only, and scoped to whoever asks."""

from __future__ import annotations

from rest_framework.test import APIClient, APITestCase

from apps.matches import services
from apps.matches.tests.factories import make_matchup
from apps.players.tests.factories import make_player


def _authed_client(player) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=player.user)
    return client


class MatchHistoryListTests(APITestCase):
    def test_lists_only_the_callers_own_matches(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        carol = make_player(email="carol@example.com")
        make_matchup(player_one=alice, player_two=bob, question_count=3)
        make_matchup(player_one=bob, player_two=carol, question_count=3)

        response = _authed_client(alice).get("/api/v1/matches/")

        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]
        self.assertEqual(len(rows), 1)


class MatchHistoryDetailTests(APITestCase):
    def test_renders_a_finished_matchup_with_the_concrete_questions(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        matchup = make_matchup(player_one=alice, player_two=bob, question_count=3)
        services.start_matchup(matchup=matchup)
        services.abandon_matchup(matchup=matchup, leaving_player=bob)

        response = _authed_client(alice).get(f"/api/v1/matches/{matchup.pk}/")

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["outcome"], "abandoned")
        self.assertEqual(len(body["questions"]), 3)
        self.assertIn("question", body["questions"][0])

    def test_a_stranger_may_not_view_a_matchup_they_did_not_play(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        stranger = make_player(email="stranger@example.com")
        matchup = make_matchup(player_one=alice, player_two=bob, question_count=3)

        response = _authed_client(stranger).get(f"/api/v1/matches/{matchup.pk}/")

        self.assertEqual(response.status_code, 403)

    def test_a_since_deactivated_question_still_renders(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        matchup = make_matchup(player_one=alice, player_two=bob, question_count=3)
        from apps.questions.selectors import QuestionRef, get_question

        first = matchup.questions.get(order=1)
        question = get_question(ref=QuestionRef(first.question_type, first.question_id))
        question.is_active = False
        question.save(update_fields=["is_active"])

        response = _authed_client(alice).get(f"/api/v1/matches/{matchup.pk}/")

        self.assertEqual(response.status_code, 200)
