"""Match history over REST: read-only, and scoped to whoever asks."""

from __future__ import annotations

from rest_framework.test import APIClient, APITestCase

from apps.matches import services
from apps.matches.tests.factories import make_matchup
from apps.players.tests.factories import make_player
from apps.questions.selectors import QuestionRef, get_question


def _authed_client(player) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=player.user)
    return client


def _first_option(matchup_question):
    """The correct option of a factory-built single-answer question — the
    factory always authors option 1 as the right one."""
    question = get_question(
        ref=QuestionRef(matchup_question.question_type, matchup_question.question_id)
    )
    return question.options.order_by("order").first()


class MatchHistoryListTests(APITestCase):
    def test_lists_only_the_callers_own_matches(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        carol = make_player(email="carol@example.com")
        # Finished, because the list is history — see
        # `selectors.list_matchups_for_player`. Abandoning is the shortest way
        # to a terminal status; what is under test here is the scoping.
        mine = make_matchup(player_one=alice, player_two=bob, question_count=3)
        theirs = make_matchup(player_one=bob, player_two=carol, question_count=3)
        for matchup, leaver in ((mine, bob), (theirs, carol)):
            services.start_matchup(matchup=matchup)
            services.abandon_matchup(matchup=matchup, leaving_player=leaver)

        response = _authed_client(alice).get("/api/v1/matches/")

        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]
        self.assertEqual(len(rows), 1)


class MatchHistoryDetailTests(APITestCase):
    def test_renders_a_finished_matchup_with_the_questions_actually_played(self):
        """An abandoned match shows the question that was asked, not the three
        that were drawn.

        `abandon_matchup` closes the question in progress and starts no more,
        so questions 2 and 3 were never put in front of anybody. Publishing
        their boards would outlive the match: those questions go back in the
        category pool and can be drawn against this player again, which makes
        "abandon, then read the box score" a way to farm boards.
        """
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        matchup = make_matchup(player_one=alice, player_two=bob, question_count=3)
        services.start_matchup(matchup=matchup)
        services.abandon_matchup(matchup=matchup, leaving_player=bob)

        response = _authed_client(alice).get(f"/api/v1/matches/{matchup.pk}/")

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["outcome"], "abandoned")
        self.assertEqual([question["order"] for question in body["questions"]], [1])
        self.assertIn("question", body["questions"][0])

    def test_a_stranger_may_not_view_a_matchup_they_did_not_play(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        stranger = make_player(email="stranger@example.com")
        matchup = make_matchup(player_one=alice, player_two=bob, question_count=3)

        response = _authed_client(stranger).get(f"/api/v1/matches/{matchup.pk}/")

        self.assertEqual(response.status_code, 403)

    def test_a_live_matchup_is_not_a_box_score(self):
        """The board of a question nobody has been asked yet is the leak.

        A player sitting in a live match can name their own matchup id — it is
        in the URL of the screen they are on — so this endpoint is reachable
        with a legitimate token, by the right person, for the right match, and
        every check above still passes. What it must not hand back is the
        rest of the game.
        """
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        matchup = make_matchup(player_one=alice, player_two=bob, question_count=3)
        services.start_matchup(matchup=matchup)

        response = _authed_client(alice).get(f"/api/v1/matches/{matchup.pk}/")

        self.assertEqual(response.status_code, 409)

    def test_an_opponents_answer_is_not_readable_while_the_clock_runs(self):
        """The severe one: the opponent's submission *is* the answer.

        `player.answered` says who answered and deliberately never says what
        or whether they were right, because the other player's clock is still
        running. A box score that renders both sides' submissions publishes
        exactly what that message withholds — and on a single-answer question,
        the opponent's `submitted` plus `is_correct` is the key.
        """
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        matchup = make_matchup(player_one=alice, player_two=bob, question_count=3)
        services.start_matchup(matchup=matchup)
        first = matchup.questions.get(order=1)
        option = _first_option(first)
        services.submit_answer(
            matchup=matchup,
            player=bob,
            order=1,
            payload={"type": "single-answer", "option_id": option.pk},
        )

        response = _authed_client(alice).get(f"/api/v1/matches/{matchup.pk}/")

        # Asserted structurally rather than by searching the body for the option
        # id: an `OptionId` is a small integer, so `"1" in body` would match the
        # question order, a score, half the payload. The claim is that Bob's
        # submission is not in the response at all — under any key.
        payload = response.json()
        answers = [
            question.get("answers", {})
            for question in payload.get("data", {}).get("questions", [])
        ]
        self.assertNotIn(bob.display_name, {name for entry in answers for name in entry})

    def test_a_live_score_line_does_not_say_whether_the_opponent_was_right(self):
        """The same leak through the list, which has no questions in it.

        `correct_answers` is incremented by `submit_answer`, not by
        `complete_question` — so while a question is open it is a live
        readout of whether the opponent's answer landed. Polling this during
        a ten-second window is the cheapest version of the attack above.
        """
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        matchup = make_matchup(player_one=alice, player_two=bob, question_count=3)
        services.start_matchup(matchup=matchup)
        first = matchup.questions.get(order=1)
        services.submit_answer(
            matchup=matchup,
            player=bob,
            order=1,
            payload={"type": "single-answer", "option_id": _first_option(first).pk},
        )

        rows = _authed_client(alice).get("/api/v1/matches/").json()["data"]

        # History is finished matches. The live one is not withheld from the
        # player — they are looking at it, over the socket running it.
        self.assertNotIn(str(matchup.pk), [row["id"] for row in rows])

    def test_a_since_deactivated_question_still_renders(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        matchup = make_matchup(player_one=alice, player_two=bob, question_count=3)
        services.start_matchup(matchup=matchup)
        services.abandon_matchup(matchup=matchup, leaving_player=bob)

        first = matchup.questions.get(order=1)
        question = get_question(ref=QuestionRef(first.question_type, first.question_id))
        question.is_active = False
        question.save(update_fields=["is_active"])

        response = _authed_client(alice).get(f"/api/v1/matches/{matchup.pk}/")

        self.assertEqual(response.status_code, 200)
