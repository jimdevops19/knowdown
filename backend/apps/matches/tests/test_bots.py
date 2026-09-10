"""apps.matches.bots: the answer builders, the roster command, and the
end-to-end matchmaking fallback over real sockets.

``BotAnswerRegistryTests`` walks ``BOT_ANSWER_BUILDERS`` the way
``apps.questions.tests.test_evaluation.RegistryCoverageTests`` walks the four
sibling registries ``backend/CLAUDE.md`` describes — a question type with no
bot builder should fail here, not surface as a bot silently sitting a live
question out. ``MatchmakingBotFallbackTests`` is ``test_realtime.py``'s own
style (``WebsocketCommunicator`` against the real consumers), the one place
this feature is only true if a socket actually sees it.
"""

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase, override_settings

from apps.matches import events
from apps.matches.authentication import JWTAuthMiddlewareStack
from apps.matches.bots.answering import BOT_ANSWER_BUILDERS, build_bot_answer
from apps.matches.models import BotProfile, Matchup
from apps.matches.routing import websocket_urlpatterns
from apps.matches.tests.factories import stock_category
from apps.players.models import Player
from apps.players.tests.factories import make_player
from apps.questions.models import QUESTION_MODELS
from apps.questions.services.evaluation import evaluate_answer
from apps.questions.tests.factories import QUESTION_FACTORIES

from .test_realtime import _connect_matchmaking, _token_query  # noqa: F401 - reused helpers

application = JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))


class BotAnswerRegistryTests(TestCase):
    def test_every_question_type_has_a_bot_builder(self):
        missing = set(QUESTION_MODELS) - set(BOT_ANSWER_BUILDERS)
        assert not missing, f"No bot answer builder for: {sorted(missing)}"

    def test_a_correct_choice_always_scores_full_credit(self):
        for question_type, make_question in QUESTION_FACTORIES.items():
            question = make_question(slug=f"bot-right-{question_type}")
            payload = build_bot_answer(question=question, correct=True)
            result = evaluate_answer(question=question, submitted=payload)
            assert result.score == 1.0, f"{question_type}: expected full credit, got {result.score}"

    def test_an_incorrect_choice_never_scores_full_credit(self):
        for question_type, make_question in QUESTION_FACTORIES.items():
            question = make_question(slug=f"bot-wrong-{question_type}")
            payload = build_bot_answer(question=question, correct=False)
            result = evaluate_answer(question=question, submitted=payload)
            assert result.score < 1.0, f"{question_type}: expected less than full credit, got {result.score}"


class SeedBotsCommandTests(TestCase):
    def test_seeding_is_idempotent_and_spans_the_requested_ranges(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_bots", "--count", "10", stdout=StringIO())
        call_command("seed_bots", "--count", "10", stdout=StringIO())  # re-run: no duplicates

        bots = Player.objects.filter(is_bot=True)
        assert bots.count() == 10

        profiles = BotProfile.objects.filter(player__in=bots).order_by("accuracy")
        weakest, strongest = profiles.first(), profiles.last()
        assert weakest.accuracy == 0.30
        assert strongest.accuracy == 0.90
        assert weakest.min_response_ms > strongest.max_response_ms


class MatchmakingBotFallbackTests(TransactionTestCase):
    @override_settings(FF_ENABLE_BOTS_IF_TIMEOUT=True, MATCHMAKING_BOT_TIMEOUT_SECONDS=0)
    async def test_a_lone_player_is_matched_with_a_bot_after_the_timeout(self):
        from io import StringIO

        from django.core.management import call_command

        await database_sync_to_async(call_command)("seed_bots", "--count", "5", stdout=StringIO())
        category = await database_sync_to_async(stock_category)()
        player = await database_sync_to_async(make_player)(email="lonely@example.com")

        communicator = WebsocketCommunicator(
            application, f"/ws/v1/matchmaking/{category.slug}/{_token_query(player)}"
        )
        connected, _ = await communicator.connect()
        assert connected
        assert (await communicator.receive_json_from(timeout=5))["type"] == events.SEARCHING

        found = await communicator.receive_json_from(timeout=5)
        assert found["type"] == events.MATCH_FOUND
        await communicator.receive_output()  # the pairing socket closes itself
        await communicator.disconnect()

        matchup = await database_sync_to_async(Matchup.objects.get)(pk=found["matchup_id"])
        opponent = await database_sync_to_async(
            lambda: matchup.players.exclude(player=player).get().player
        )()
        assert opponent.is_bot

    @override_settings(FF_ENABLE_BOTS_IF_TIMEOUT=True, MATCHMAKING_BOT_TIMEOUT_SECONDS=0)
    async def test_the_bot_plays_its_side_to_a_finished_matchup(self):
        from io import StringIO

        from unittest import mock

        from django.core.management import call_command

        from .test_realtime import _connect_matchup

        # A fast, accurate bot — the point of this test is that the game
        # *finishes*, not any particular score. The human player connects to
        # the matchup socket but never answers: what forces each question
        # closed is its own connect-time watchdog racing the bot's answer,
        # the same as a real client that stalls on one question would —
        # which is why FALLBACK_QUESTION_TIME_LIMIT_MS is patched low rather
        # than the test waiting out the real ten seconds per question.
        await database_sync_to_async(call_command)("seed_bots", "--count", "1", stdout=StringIO())
        await database_sync_to_async(BotProfile.objects.update)(
            accuracy=1.0, min_response_ms=1, max_response_ms=5
        )
        # The default count (10) — not fewer: MATCH_QUESTION_COUNTS draws up
        # to 7, and a thinner category would make create_matchup itself
        # refuse (the same "a thin category is a broken match" rule
        # backend/CLAUDE.md documents for apps.questions), independent of
        # anything this test is actually about.
        category = await database_sync_to_async(stock_category)()
        player = await database_sync_to_async(make_player)(email="vs-bot@example.com")

        with mock.patch("apps.matches.constants.FALLBACK_QUESTION_TIME_LIMIT_MS", 100):
            communicator = WebsocketCommunicator(
                application, f"/ws/v1/matchmaking/{category.slug}/{_token_query(player)}"
            )
            connected, _ = await communicator.connect()
            assert connected
            await communicator.receive_json_from(timeout=5)
            found = await communicator.receive_json_from(timeout=5)
            await communicator.receive_output()
            await communicator.disconnect()

            matchup_socket = await _connect_matchup(player, found["matchup_id"])
            outcome = None
            for _ in range(100):  # one QUESTION_STARTED/PLAYER_ANSWERED/QUESTION_RESULT per question
                message = await matchup_socket.receive_json_from(timeout=5)
                if message["type"] == events.MATCH_COMPLETED:
                    outcome = message
                    break
            await matchup_socket.disconnect()

        assert outcome is not None, "matchup never reached MATCH_COMPLETED"
        assert outcome["outcome"] == Matchup.Outcome.PLAYED
