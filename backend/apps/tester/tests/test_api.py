"""The rehearsal room, and the two locks on its door.

The suite is organised around what could go wrong, worst first: the surface is
reachable by somebody who is not a maintainer; the surface is reachable on a
tier that did not ask for it; and only then whether it does its job.
"""

from __future__ import annotations

from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User
from apps.players.services import ensure_player_for_user
from apps.questions.models import QUESTION_MODELS
from apps.questions.tests.factories import (
    make_category,
    make_free_text,
    make_gradual_hints,
    make_matrix,
    make_ordering,
    make_single_answer,
)

PASSWORD = "correct-horse-19"


def make_maintainer(email: str = "boss@example.com") -> User:
    """An account as ``manage.py createsuperuser`` would leave it.

    ``create_superuser`` rather than ``create_user(is_staff=True)`` on purpose:
    the permission's whole claim is that it recognises the accounts that command
    makes, and a fixture that sets the flag by hand would prove something
    slightly different.
    """
    user = User.objects.create_superuser(email=email, password=PASSWORD)
    ensure_player_for_user(user=user)
    return user


def make_ordinary_player(email: str = "player@example.com") -> User:
    user = User.objects.create_user(email=email, password=PASSWORD)
    ensure_player_for_user(user=user)
    return user


def client_for(user: User | None) -> APIClient:
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return client


class DoorTests(APITestCase):
    """Who gets in. Every endpoint, not just one — the gate is per view, so a
    test of one view proves one view."""

    def setUp(self):
        self.question = make_single_answer(slug="door-test")
        self.paths = [
            "/api/v1/tester/config/",
            "/api/v1/tester/questions/",
            f"/api/v1/tester/questions/single-answer/{self.question.id}/",
            f"/api/v1/tester/questions/single-answer/{self.question.id}/answer-key/",
        ]

    def test_an_anonymous_caller_is_refused_everywhere(self):
        for path in self.paths:
            with self.subTest(path=path):
                self.assertEqual(client_for(None).get(path).status_code, 401)

    def test_a_signed_in_player_who_is_not_staff_is_refused_everywhere(self):
        """The case this whole feature turns on.

        An ordinary account is a perfectly valid, fully authenticated user of
        this platform, and it must still bounce off every one of these — the
        surface publishes answer keys for questions that are still in the pool,
        so "signed in" is not the bar.
        """
        player = make_ordinary_player()
        for path in self.paths:
            with self.subTest(path=path):
                self.assertEqual(client_for(player).get(path).status_code, 403)

    def test_posting_an_answer_is_refused_for_a_non_staff_player(self):
        response = client_for(make_ordinary_player()).post(
            f"/api/v1/tester/questions/single-answer/{self.question.id}/answer/",
            {"submitted": {"type": "single-answer", "option_id": 1}},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_a_staff_account_is_let_in(self):
        staff = make_maintainer()
        for path in self.paths:
            with self.subTest(path=path):
                self.assertEqual(client_for(staff).get(path).status_code, 200)

    def test_staff_status_is_read_at_request_time(self):
        """Demoting an account closes the door on it, with no token to revoke.

        Deliberately driven through a **real access token** rather than
        ``force_authenticate``: that helper pins a user object onto the client,
        so it would keep answering from the copy made before the demotion and
        prove nothing. What is under test is that the permission reads
        ``is_staff`` off the row on every request — so a maintainer who is stood
        down loses the tester on their next click, while an access token minted
        while they were staff is still perfectly valid for everything else.
        """
        staff = make_maintainer()
        token = (
            APIClient()
            .post(
                "/api/v1/auth/token/",
                {"email": staff.email, "password": PASSWORD},
                format="json",
            )
            .json()["data"]["access"]
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(client.get("/api/v1/tester/config/").status_code, 200)

        User.objects.filter(pk=staff.pk).update(is_staff=False)

        self.assertEqual(client.get("/api/v1/tester/config/").status_code, 403)


class CatalogTests(APITestCase):
    def setUp(self):
        self.staff = make_maintainer()
        self.client = client_for(self.staff)
        self.nba = make_category(slug="nba", name="NBA")
        self.f1 = make_category(slug="f1", name="Formula 1")

    def rows(self, query: str = ""):
        response = self.client.get(f"/api/v1/tester/questions/{query}")
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]

    def test_lists_every_answer_shape_in_one_page(self):
        """The point of the catalog: eight tables, one list.

        A maintainer looking for "that grid question" does not know which table
        it is in, and should not have to.
        """
        make_single_answer(slug="one", category=self.nba)
        make_free_text(slug="two", category=self.nba)
        make_ordering(slug="three", category=self.nba)
        make_matrix(slug="four", category=self.nba)

        types = {row["type"] for row in self.rows()}

        self.assertEqual(types, {"single-answer", "free-text", "ordering", "matrix"})

    def test_a_card_carries_the_slug_a_play_time_board_withholds(self):
        make_single_answer(slug="kobe-81-point-game", category=self.nba)

        (row,) = self.rows()

        self.assertEqual(row["slug"], "kobe-81-point-game")
        self.assertEqual(row["category"], "nba")
        self.assertEqual(row["category_name"], "NBA")
        self.assertTrue(row["is_active"])

    def test_deactivated_questions_are_listed_by_default(self):
        """The opposite default from ``available_questions``, and deliberately.

        "Why does this question never come up" is answered by seeing it in the
        list with a badge on it, not by an empty search.
        """
        make_single_answer(slug="retired", category=self.nba).__class__.objects.filter(
            slug="retired"
        ).update(is_active=False)

        (row,) = self.rows()

        self.assertFalse(row["is_active"])

    def test_include_inactive_false_hides_them(self):
        live = make_single_answer(slug="live", category=self.nba)
        type(live).objects.create(
            slug="retired",
            description="A question.",
            level=3,
            category=self.nba,
            is_active=False,
        )

        rows = self.rows("?include_inactive=false")

        self.assertEqual([row["slug"] for row in rows], ["live"])

    def test_search_matches_slug_text_and_category_name(self):
        make_single_answer(slug="kobe-81", category=self.nba)
        make_free_text(slug="senna", category=self.f1)

        self.assertEqual([row["slug"] for row in self.rows("?search=kobe")], ["kobe-81"])
        self.assertEqual([row["slug"] for row in self.rows("?search=Formula")], ["senna"])
        # The description every factory writes, so this matches both.
        self.assertEqual(len(self.rows("?search=A question")), 2)

    def test_filters_by_category_type_and_level(self):
        make_single_answer(slug="easy-nba", category=self.nba, level=2)
        make_single_answer(slug="hard-nba", category=self.nba, level=9)
        make_free_text(slug="f1-text", category=self.f1, level=2)

        self.assertEqual(
            {row["slug"] for row in self.rows("?category=nba")},
            {"easy-nba", "hard-nba"},
        )
        self.assertEqual(
            [row["slug"] for row in self.rows("?type=free-text")], ["f1-text"]
        )
        self.assertEqual(
            {row["slug"] for row in self.rows("?level_min=1&level_max=3")},
            {"easy-nba", "f1-text"},
        )

    def test_an_impossible_level_range_is_refused_rather_than_answered_empty(self):
        response = self.client.get("/api/v1/tester/questions/?level_min=9&level_max=2")

        self.assertEqual(response.status_code, 400)

    def test_created_after_filters_to_what_a_sync_just_wrote(self):
        """The review workflow this filter exists for: skim today's batch."""
        old = make_single_answer(slug="old", category=self.nba)
        type(old).objects.filter(slug="old").update(
            created_at="2020-01-01T00:00:00Z"
        )
        make_single_answer(slug="fresh", category=self.nba)

        rows = self.rows("?created_after=2026-01-01")

        self.assertEqual([row["slug"] for row in rows], ["fresh"])

    def test_created_after_accepts_a_full_timestamp_and_sorts_newest_first(self):
        first = make_single_answer(slug="first", category=self.nba)
        type(first).objects.filter(slug="first").update(
            created_at="2020-01-01T00:00:00Z"
        )
        make_single_answer(slug="second", category=self.nba)
        type(first).objects.filter(slug="second").update(
            created_at="2020-01-02T00:00:00Z"
        )
        make_single_answer(slug="third", category=self.nba)
        type(first).objects.filter(slug="third").update(
            created_at="2020-01-03T00:00:00Z"
        )

        rows = self.rows("?created_after=2020-01-01T12:00:00Z")

        self.assertEqual([row["slug"] for row in rows], ["third", "second"])

    def test_a_malformed_created_after_is_refused(self):
        response = self.client.get("/api/v1/tester/questions/?created_after=not-a-date")

        self.assertEqual(response.status_code, 400)

    def test_config_counts_the_catalog_for_the_filter_bar(self):
        make_single_answer(slug="one", category=self.nba)
        make_free_text(slug="two", category=self.f1)

        body = self.client.get("/api/v1/tester/config/").json()["data"]

        self.assertTrue(body["enabled"])
        self.assertEqual(body["question_count"], 2)
        self.assertEqual(
            {row["slug"]: row["question_count"] for row in body["categories"]},
            {"nba": 1, "f1": 1},
        )
        # Every type, including the empty ones — a type with nothing authored
        # still needs somewhere to click.
        self.assertEqual(len(body["types"]), len(QUESTION_MODELS))


class RehearsalTests(APITestCase):
    def setUp(self):
        self.client = client_for(make_maintainer())

    def test_serves_the_same_board_a_match_would(self):
        question = make_single_answer(slug="board")

        body = self.client.get(
            f"/api/v1/tester/questions/single-answer/{question.id}/"
        ).json()["data"]

        self.assertEqual(body["board"]["type"], "single-answer")
        self.assertEqual(len(body["board"]["options"]), 3)
        # The anti-cheat guarantee is inherited, not re-decided: the board comes
        # out of `serialize_for_play`, so it cannot name the answer here either.
        self.assertNotIn("is_correct", str(body["board"]))

    def test_carries_the_clock_a_match_would_run(self):
        question = make_single_answer(slug="clocked")
        type(question).objects.filter(pk=question.pk).update(time_limit_seconds=42)

        body = self.client.get(
            f"/api/v1/tester/questions/single-answer/{question.id}/"
        ).json()["data"]

        self.assertEqual(body["time_limit_ms"], 42_000)
        self.assertEqual(body["read_delay_ms"], 3_000)

    def test_the_board_order_is_stable_until_the_seed_changes(self):
        """A reload must not reshuffle the options under somebody reading them,
        and asking for a new deal must actually deal again."""
        question = make_ordering(slug="shuffled", items=tuple(str(n) for n in range(1, 9)))
        path = f"/api/v1/tester/questions/ordering/{question.id}/"

        first = self.client.get(path).json()["data"]["board"]["options"]
        again = self.client.get(path).json()["data"]["board"]["options"]
        reseeded = self.client.get(f"{path}?seed=other").json()["data"]["board"]["options"]

        self.assertEqual(first, again)
        self.assertNotEqual(first, reseeded)

    def test_a_gradual_hints_rehearsal_carries_the_whole_schedule(self):
        """The one payload here that says more than a live board may.

        A live board carries the *shape* of the reveal and the socket pays the
        text out on a timer; there is no socket in a rehearsal, so the schedule
        comes down whole and the client replays it. Without this the one
        question type most worth rehearsing could not be rehearsed at all.
        """
        question = make_gradual_hints(slug="clues")

        body = self.client.get(
            f"/api/v1/tester/questions/gradual-hints/{question.id}/"
        ).json()["data"]

        self.assertTrue(body["hints"])
        self.assertEqual(body["hints"][0]["offset_ms"], 0)
        self.assertEqual(
            [hint["index"] for hint in body["hints"]],
            list(range(1, len(body["hints"]) + 1)),
        )
        # And the board it sits beside still does not carry them.
        self.assertNotIn("hints", body["board"])

    def test_every_other_type_has_an_empty_schedule(self):
        question = make_single_answer(slug="no-clues")

        body = self.client.get(
            f"/api/v1/tester/questions/single-answer/{question.id}/"
        ).json()["data"]

        self.assertEqual(body["hints"], [])

    def test_an_unknown_question_is_a_404(self):
        response = self.client.get(
            "/api/v1/tester/questions/single-answer/"
            "00000000-0000-0000-0000-000000000000/"
        )

        self.assertEqual(response.status_code, 404)

    def test_an_unknown_question_type_is_a_404(self):
        question = make_single_answer(slug="mistyped")

        response = self.client.get(
            f"/api/v1/tester/questions/no-such-type/{question.id}/"
        )

        self.assertEqual(response.status_code, 404)


class AnswerTests(APITestCase):
    def setUp(self):
        self.client = client_for(make_maintainer())

    def answer(self, question, submitted, **extra):
        return self.client.post(
            f"/api/v1/tester/questions/{question.question_type}/{question.id}/answer/",
            {"submitted": submitted, **extra},
            format="json",
        )

    def test_a_right_answer_comes_back_marked_with_its_key(self):
        question = make_single_answer(slug="marked")
        correct = question.options.get(is_correct=True)

        body = self.answer(
            question, {"type": "single-answer", "option_id": correct.id}
        ).json()["data"]

        self.assertTrue(body["is_correct"])
        self.assertEqual(body["score"], 1.0)
        self.assertEqual(body["answer_key"]["option_ids"], [correct.id])

    def test_a_wrong_answer_is_told_what_was_right(self):
        """The whole reason the key rides on the verdict rather than behind a
        second request: a wrong answer is when you most need it."""
        question = make_single_answer(slug="wrong")
        wrong = question.options.filter(is_correct=False).first()
        correct = question.options.get(is_correct=True)

        body = self.answer(
            question, {"type": "single-answer", "option_id": wrong.id}
        ).json()["data"]

        self.assertFalse(body["is_correct"])
        self.assertEqual(body["points"], 0)
        self.assertEqual(body["answer_key"]["option_ids"], [correct.id])

    def test_partial_credit_is_reported_as_a_score_not_a_verdict(self):
        """A grid with one cell wrong is ``false`` *and* worth something, and a
        tool that reported only the boolean would hide the most common thing
        worth knowing about a matrix."""
        question = make_matrix(slug="grid")
        cells = list(question.cells.select_related("row", "column").all())
        submitted = {
            "type": "matrix",
            "cells": [
                {
                    "row_id": cell.row_id,
                    "column_id": cell.column_id,
                    "answer": (
                        cell.answers.first().value if index else "definitely not"
                    ),
                }
                for index, cell in enumerate(cells)
            ],
        }

        body = self.answer(question, submitted).json()["data"]

        self.assertFalse(body["is_correct"])
        self.assertGreater(body["score"], 0)
        self.assertLess(body["score"], 1)

    def test_points_follow_the_rehearsed_clock(self):
        """Speed is scored here the way it is scored in a match — by the same
        function — so a fast answer must be worth more than a slow one."""
        question = make_single_answer(slug="timed")
        correct = question.options.get(is_correct=True)
        submitted = {"type": "single-answer", "option_id": correct.id}

        fast = self.answer(question, submitted, elapsed_ms=0).json()["data"]
        slow = self.answer(question, submitted, elapsed_ms=9_000).json()["data"]

        self.assertGreater(fast["points"], slow["points"])

    def test_a_rehearsed_clock_is_clamped_to_the_question(self):
        question = make_single_answer(slug="clamped")
        correct = question.options.get(is_correct=True)

        body = self.answer(
            question,
            {"type": "single-answer", "option_id": correct.id},
            elapsed_ms=10_000_000,
        ).json()["data"]

        self.assertEqual(body["elapsed_ms"], body["time_limit_ms"])

    def test_a_malformed_payload_is_refused_the_way_a_socket_would_refuse_it(self):
        question = make_single_answer(slug="malformed")

        response = self.answer(question, {"type": "single-answer"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "malformed_answer")

    def test_answering_with_the_wrong_type_is_refused(self):
        question = make_single_answer(slug="mismatched")

        response = self.answer(question, {"type": "true-false", "answer": True})

        self.assertEqual(response.status_code, 400)

    def test_a_free_text_key_floats_the_spelling_that_was_typed(self):
        question = make_free_text(slug="spelled", accepted=("Kobe Bryant", "Kobe"))

        body = self.answer(question, {"type": "free-text", "text": "kobe"}).json()["data"]

        self.assertTrue(body["is_correct"])
        self.assertEqual(body["answer_key"]["accepted"][0], "Kobe")

    def test_the_key_can_be_asked_for_without_answering(self):
        question = make_free_text(slug="just-tell-me", accepted=("Kobe Bryant",))

        body = self.client.get(
            f"/api/v1/tester/questions/free-text/{question.id}/answer-key/"
        ).json()["data"]

        self.assertEqual(body["type"], "free-text")
        self.assertEqual(body["accepted"], ["Kobe Bryant"])

    def test_a_rehearsal_records_nothing(self):
        """No matchup, no answer row, no rating.

        Answering the same question forty times while fixing its accepted
        spellings is the normal way to use this page, and it must leave the
        database exactly as it found it.
        """
        from apps.matches.models import Matchup, PlayerAnswer

        question = make_single_answer(slug="no-trace")
        correct = question.options.get(is_correct=True)

        self.answer(question, {"type": "single-answer", "option_id": correct.id})

        self.assertEqual(Matchup.objects.count(), 0)
        self.assertEqual(PlayerAnswer.objects.count(), 0)
