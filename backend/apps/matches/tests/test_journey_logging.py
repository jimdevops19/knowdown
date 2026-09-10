"""The route through the product, not just its endpoints (`plan.md` step 25).

"Player queued", "Match found", "Question answered" and "Match completed" are
each one log line with ``action`` set to a fixed, queryable verb — see
``apps.matches.consumers`` and ``apps.matches.services`` for where they are
written, and ``backend/CLAUDE.md``'s Realtime section for the convention.
These tests read them back the way an operator's log query would: filter on
``action``, not on the human sentence beside it.
"""

from __future__ import annotations

import asyncio

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.matches import selectors, services
from apps.matches.authentication import JWTAuthMiddlewareStack
from apps.matches.routing import websocket_urlpatterns
from apps.matches.tests.factories import make_matchup, stock_category
from apps.players.tests.factories import make_player
from apps.questions.selectors import QuestionRef
from apps.questions.selectors import get_question as get_concrete_question

application = JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))


def _correct_option_id(question) -> int:
    return question.options.get(is_correct=True).id


def _actions(captured) -> list[str]:
    """The ``action`` field off every captured record that carries one —
    reading ``json_fields`` the way ``shared.logging.formatter.JSONFormatter``
    would, not the rendered sentence."""
    found = []
    for record in captured.records:
        fields = getattr(record, "json_fields", None)
        if fields and "action" in fields:
            found.append(fields["action"])
    return found


def _fields_for(captured, action: str) -> dict:
    for record in captured.records:
        fields = getattr(record, "json_fields", None)
        if fields and fields.get("action") == action:
            return fields
    raise AssertionError(f"No log line with action={action!r} among {_actions(captured)!r}")


class QuestionAnsweredJourneyTests(TestCase):
    def test_answering_logs_the_action_and_the_time_it_took(self) -> None:
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        alice, bob = [side.player for side in selectors.matchup_players(matchup=matchup)]
        question = selectors.get_matchup_question(matchup=matchup, order=1)
        concrete = get_concrete_question(
            ref=QuestionRef(question.question_type, question.question_id)
        )

        with self.assertLogs("apps.matches.services", level="INFO") as captured:
            services.submit_answer(
                matchup=matchup,
                player=alice,
                order=1,
                payload={"type": "single-answer", "option_id": _correct_option_id(concrete)},
            )

        self.assertIn("answered", _actions(captured))
        fields = _fields_for(captured, "answered")
        self.assertEqual(fields["player"], alice.display_name)
        self.assertIsInstance(fields["duration_ms"], int)
        self.assertGreaterEqual(fields["duration_ms"], 0)


class MatchCompletedJourneyTests(TestCase):
    def test_a_played_match_logs_completed_once(self) -> None:
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        alice, bob = [side.player for side in selectors.matchup_players(matchup=matchup)]

        with self.assertLogs("apps.matches.services", level="INFO") as captured:
            for order in range(1, 4):
                question = selectors.get_matchup_question(matchup=matchup, order=order)
                concrete = get_concrete_question(
                    ref=QuestionRef(question.question_type, question.question_id)
                )
                correct = _correct_option_id(concrete)
                wrong = next(o.id for o in concrete.options.all() if o.id != correct)
                services.submit_answer(
                    matchup=matchup, player=alice, order=order,
                    payload={"type": "single-answer", "option_id": correct},
                )
                services.submit_answer(
                    matchup=matchup, player=bob, order=order,
                    payload={"type": "single-answer", "option_id": wrong},
                )

        completed = [a for a in _actions(captured) if a == "completed"]
        self.assertEqual(len(completed), 1)  # idempotent, not once per question
        fields = _fields_for(captured, "completed")
        self.assertEqual(fields["player"], alice.display_name)  # the winner
        self.assertIsInstance(fields["duration_ms"], int)

    def test_an_abandoned_match_logs_completed_too(self) -> None:
        matchup = make_matchup(question_count=3)
        services.start_matchup(matchup=matchup)
        alice, bob = [side.player for side in selectors.matchup_players(matchup=matchup)]

        with self.assertLogs("apps.matches.services", level="INFO") as captured:
            services.abandon_matchup(matchup=matchup, leaving_player=bob)

        self.assertIn("completed", _actions(captured))
        fields = _fields_for(captured, "completed")
        self.assertEqual(fields["player"], alice.display_name)  # bob left; alice wins


class PoolJourneyTests(TransactionTestCase):
    """"Player queued" and "Match found" — over real sockets, since both are
    written from `apps.matches.consumers`, not `services`."""

    def _token_query(self, player) -> str:
        return f"?token={AccessToken.for_user(player.user)}"

    async def test_queueing_then_matching_logs_both_actions(self) -> None:
        category = await asyncio.get_event_loop().run_in_executor(None, stock_category)
        alice = await asyncio.get_event_loop().run_in_executor(
            None, lambda: make_player(email="queue-alice@example.com")
        )
        bob = await asyncio.get_event_loop().run_in_executor(
            None, lambda: make_player(email="queue-bob@example.com")
        )

        with self.assertLogs("apps.matches.consumers", level="INFO") as captured:
            first = WebsocketCommunicator(
                application, f"/ws/v1/matchmaking/{category.slug}/{self._token_query(alice)}"
            )
            connected, _ = await first.connect()
            self.assertTrue(connected)
            await first.receive_json_from(timeout=5)  # SEARCHING

            second = WebsocketCommunicator(
                application, f"/ws/v1/matchmaking/{category.slug}/{self._token_query(bob)}"
            )
            connected, _ = await second.connect()
            self.assertTrue(connected)
            await first.receive_json_from(timeout=5)  # MATCH_FOUND
            await second.receive_json_from(timeout=5)  # MATCH_FOUND

            await first.disconnect()
            await second.disconnect()

        actions = _actions(captured)
        self.assertIn("queued", actions)
        self.assertIn("matched", actions)
        matched_fields = _fields_for(captured, "matched")
        self.assertIsInstance(matched_fields["duration_ms"], int)
        self.assertGreaterEqual(matched_fields["duration_ms"], 0)
