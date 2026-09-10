"""Match history over REST — read-only, and always about a finished game.

Reuses ``apps.questions.api.serializers.serialize_for_play`` for the question
payload rather than inventing a second one: a box score gets the same board a
player saw while the clock ran, never the raw question row, so this layer
inherits the anti-cheat guarantee instead of re-deciding it. What a box score
adds beyond that board is each side's own submission and its verdict — never
the *other* player's presumed-correct answer dressed up as "the answer".
"""

from __future__ import annotations

from rest_framework import serializers

from apps.players.api.serializers import PlayerSerializer
from apps.questions.api.serializers import serialize_for_play
from apps.questions.selectors import QuestionRef, get_question


class PlayerAnswerSerializer(serializers.Serializer):
    """One player's own submission to one question — never the opponent's."""

    submitted = serializers.JSONField(source="answer")
    is_correct = serializers.BooleanField()
    score = serializers.FloatField()
    points = serializers.IntegerField()
    response_time_ms = serializers.IntegerField()
    answered_at = serializers.DateTimeField()


class MatchupQuestionSerializer(serializers.Serializer):
    """One question of the match, as it was played, plus who answered what.

    Resolved through ``questions.selectors.get_question`` — per
    ``question_type``/``question_id`` — rather than a foreign key, which is
    exactly what lets a since-deactivated question still render here.
    """

    order = serializers.IntegerField()
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField()
    question = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()

    def get_question(self, matchup_question) -> dict:
        question = get_question(
            ref=QuestionRef(matchup_question.question_type, matchup_question.question_id)
        )
        return serialize_for_play(question=question, matchup_id=matchup_question.matchup_id)

    def get_answers(self, matchup_question) -> dict:
        # An open question publishes nobody's answer. The view above already
        # refuses a live matchup outright, and this is the second mechanism
        # behind that one: the first player to answer does so while the second
        # player's clock is still running, so `submitted` + `is_correct` on an
        # unclosed question is the answer key handed to the person still
        # thinking. A future caller that serializes a matchup without checking
        # its status gets an empty dict rather than a leak.
        if matchup_question.completed_at is None:
            return {}
        return {
            answer.player.display_name: PlayerAnswerSerializer(answer).data
            for answer in matchup_question.answers.select_related("player").all()
        }


class MatchupPlayerSerializer(serializers.Serializer):
    """One side of the result — the score line a scoreboard shows."""

    player = PlayerSerializer()
    score = serializers.IntegerField()
    correct_answers = serializers.IntegerField()
    total_answer_time_ms = serializers.IntegerField()
    is_winner = serializers.BooleanField()
    left_at = serializers.DateTimeField(allow_null=True)


class MatchupListSerializer(serializers.Serializer):
    """One row of ``GET /api/v1/matches/`` — enough to render a history list
    without resolving every question in every past match."""

    id = serializers.UUIDField()
    category = serializers.CharField(source="category.slug")
    question_count = serializers.IntegerField()
    status = serializers.CharField()
    outcome = serializers.CharField()
    is_ranked = serializers.BooleanField()
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    players = MatchupPlayerSerializer(many=True)


class MatchupDetailSerializer(MatchupListSerializer):
    """A full box score — ``GET /api/v1/matches/{id}/``."""

    questions = serializers.SerializerMethodField()

    def get_questions(self, matchup) -> list[dict]:
        # Only questions that have been played. A question the server has not
        # started yet is one neither player has seen, and its board is the next
        # round of a race in progress — the same reason `get_answers` above
        # withholds an open question's verdicts. Paired with the view's status
        # gate this is belt and braces on a finished matchup, where every
        # question is closed anyway; it is the whole guard for any caller that
        # reaches this serializer another way.
        return MatchupQuestionSerializer(
            matchup.questions.filter(completed_at__isnull=False).order_by("order"),
            many=True,
        ).data
