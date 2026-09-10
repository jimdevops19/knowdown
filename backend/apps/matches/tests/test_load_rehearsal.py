"""``load_rehearsal`` / ``load_rehearsal_teardown`` — the parts testable
without a live deployment to point a real socket at: the answer-payload
builder (every branch has to match ``schemas.answers.AnswerSubmission``'s
shape or the server refuses it), the ws:// URL derivation, and teardown's
tagging — including that it leaves a played match alone.
"""

from __future__ import annotations

import random

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.matches import selectors, services
from apps.matches.management.commands.load_rehearsal import (
    EMAIL_DOMAIN,
    _answer_payload,
    _ws_base,
)
from apps.matches.tests.factories import make_matchup
from apps.players.tests.factories import make_player
from apps.questions.api.serializers import serialize_for_play
from apps.questions.selectors import QuestionRef
from apps.questions.selectors import get_question as get_concrete_question
from apps.questions.tests.factories import make_matrix


class WsBaseTests(TestCase):
    def test_https_becomes_wss(self) -> None:
        self.assertEqual(_ws_base("https://staging.knowdown.app"), "wss://staging.knowdown.app")

    def test_http_becomes_ws(self) -> None:
        self.assertEqual(_ws_base("http://localhost:8000"), "ws://localhost:8000")


class AnswerPayloadTests(TestCase):
    """Every branch has to be a payload the real server accepts — proved
    against the real served board and the real evaluator, not a hand-written
    fixture that could drift from what ``serialize_for_play`` actually sends."""

    def _board_for(self, matchup, order: int) -> dict:
        question = selectors.get_matchup_question(matchup=matchup, order=order)
        concrete = get_concrete_question(
            ref=QuestionRef(question.question_type, question.question_id)
        )
        return serialize_for_play(question=concrete, matchup_id=matchup.id), question, concrete

    def test_every_type_in_the_stock_catalog_answers_without_a_server_refusal(self) -> None:
        """Plays every question the stock category offers (single/image
        types at minimum) and confirms the built payload is accepted by the
        real service — a 200 on `submit_answer`, not a `ValidationFailed`."""
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        alice, bob = [side.player for side in selectors.matchup_players(matchup=matchup)]
        rng = random.Random(0)

        for order in range(1, 4):
            board, question, _ = self._board_for(matchup, order)
            # Both sides answer — the second is what advances the matchup to
            # its next question, the same as a real match.
            for player in (alice, bob):
                payload = _answer_payload(board, rng)
                self.assertEqual(payload["type"], board["type"])
                # Raises ValidationFailed (a test failure) if the payload's
                # shape is not one the server accepts.
                services.submit_answer(matchup=matchup, player=player, order=order, payload=payload)

    def test_matrix_cells_are_answered(self) -> None:
        question = make_matrix()
        board = serialize_for_play(question=question, matchup_id="00000000-0000-0000-0000-000000000000")
        payload = _answer_payload(board, random.Random(0))
        self.assertEqual(payload["type"], "matrix")
        self.assertEqual(len(payload["cells"]), len(board["cells"]))
        answered = {(c["row_id"], c["column_id"]) for c in payload["cells"]}
        served = {(c["row_id"], c["column_id"]) for c in board["cells"]}
        self.assertEqual(answered, served)


class TeardownTests(TestCase):
    def setUp(self) -> None:
        self.run_id = "run123"
        self.tagged = User.objects.create_user(
            email=f"loadrehearsal-{self.run_id}-0@{EMAIL_DOMAIN}", password="x" * 12
        )
        self.other_run = User.objects.create_user(
            email=f"loadrehearsal-other-0@{EMAIL_DOMAIN}", password="x" * 12
        )
        self.ordinary = make_player(email="not-a-rehearsal-account@example.com").user

    def test_it_deletes_only_the_tagged_run(self) -> None:
        call_command("load_rehearsal_teardown", run=self.run_id)
        self.assertFalse(User.objects.filter(pk=self.tagged.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.other_run.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.ordinary.pk).exists())

    def test_dry_run_deletes_nothing(self) -> None:
        call_command("load_rehearsal_teardown", run=self.run_id, dry_run=True)
        self.assertTrue(User.objects.filter(pk=self.tagged.pk).exists())

    def test_an_unknown_run_deletes_nothing_and_does_not_error(self) -> None:
        call_command("load_rehearsal_teardown", run="no-such-run")
        self.assertEqual(User.objects.count(), 3)

    def test_a_played_match_is_left_alone(self) -> None:
        """The account is removable; the history it played is not
        (``MatchupPlayer.player`` is ``PROTECT``) — teardown must not even
        attempt to touch it."""
        player = make_player(email=f"loadrehearsal-{self.run_id}-1@{EMAIL_DOMAIN}")
        matchup = make_matchup(question_count=3, player_one=player)
        call_command("load_rehearsal_teardown", run=self.run_id)
        # The account is gone (Player.user is SET_NULL); the matchup and its
        # Player row remain exactly as PROTECT requires.
        self.assertFalse(User.objects.filter(pk=player.user.pk).exists())
        matchup.refresh_from_db()
        self.assertEqual(matchup.players.count(), 2)
