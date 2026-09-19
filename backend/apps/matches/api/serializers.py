"""Match history over REST — read-only, and always about a finished game.

Reuses ``apps.questions.api.serializers.serialize_for_play`` for the question
payload rather than inventing a second one: a box score gets the same board a
player saw while the clock ran, never the raw question row, so this layer
inherits the anti-cheat guarantee instead of re-deciding it.

On top of that board it adds two things, and they are different in kind:

- **each side's own submission and verdict**, which are facts about the match;
- **``answer_key`` — what was actually right**, which is a fact about the
  *question*, and the one thing this module publishes that the play-time layer
  exists to withhold.

The second is a deliberate exception, and this is where the reasoning for it
lives, because this is the only place that takes it. A box score is read after
the whistle by the two people who just played, and "you got it wrong" without
"and here is the answer" is a scoreboard, not a post-mortem. The cost is real
and is worth naming: a question whose key somebody has read can be drawn again,
against an opponent who has not — so the exception is bounded by
``MatchHistoryDetailView``'s two gates (only the players, and only once the
match is over) and by this serializer's own ``completed_at`` check, which is the
second mechanism behind the first. The key is built by
``apps.questions.api.reveal``, a module that deliberately sits outside the
anti-cheat surface rather than punching a hole in it.

The opponent's presumed-correct answer is still never dressed up as "the
answer" — that was the old workaround for not having a key, and having one is
what retires it.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.players.api.serializers import PlayerSerializer
from apps.questions.api.reveal import serialize_answer_key
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
    #: Sudden death — a question drawn past ``Matchup.question_count`` because
    #: the match was level when the agreed board ran out
    #: (``services.tiebreak``). Published so a box score can say why a
    #: three-question match has a fourth line in it.
    is_tiebreaker = serializers.BooleanField()
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField()
    question = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()
    answer_key = serializers.SerializerMethodField()

    def _question(self, matchup_question):
        """The question row, resolved once per record.

        ``get_question`` is a query, and both ``question`` and ``answer_key``
        want the same row — cached on the instance rather than looked up twice,
        since a seven-question box score would otherwise double its queries for
        nothing.
        """
        cached = getattr(matchup_question, "_resolved_question", None)
        if cached is None:
            cached = get_question(
                ref=QuestionRef(
                    matchup_question.question_type, matchup_question.question_id
                )
            )
            matchup_question._resolved_question = cached
        return cached

    def get_question(self, matchup_question) -> dict:
        return serialize_for_play(
            question=self._question(matchup_question),
            matchup_id=matchup_question.matchup_id,
        )

    def get_answer_key(self, matchup_question) -> dict | None:
        """What was actually right — or ``None`` while the question is open.

        The same gate ``get_answers`` below applies, and for a sharper reason:
        an open question's key is the answer handed to a player whose clock is
        still running, which is the whole thing the platform is built not to do.
        A caller that reaches this serializer without checking the matchup's
        status gets ``None`` rather than a key.

        The viewer's own submission goes in so the reveal can float what *they*
        said to the front of a truncated pool. It orders the answer; it never
        decides it.
        """
        if matchup_question.completed_at is None:
            return None
        return serialize_answer_key(
            question=self._question(matchup_question),
            submitted=self._viewers_submission(matchup_question),
        )

    def _viewers_submission(self, matchup_question):
        """What the player *reading this box score* sent, if anything.

        ``None`` covers both "ran out of time" and "no viewer in context" — a
        pool shown in its authored order is a correct answer to the question
        either way, so neither case needs to be told apart here.
        """
        viewer = self.context.get("viewer")
        if viewer is None:
            return None
        answer = next(
            (
                answer
                for answer in matchup_question.answers.all()
                if answer.player_id == viewer.id
            ),
            None,
        )
        return answer.answer if answer else None

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


class MatchupParticipantSerializer(serializers.Serializer):
    """One side of a matchup, name and picture only — safe to read while the
    match is still live.

    Deliberately not ``MatchupPlayerSerializer`` below: ``score`` and
    ``correct_answers`` update the moment an answer *lands*
    (``services.submit_answer``), not when the question closes, so handing
    them out mid-match is the same opponent's-answer leak
    ``selectors.list_matchups_for_player`` and ``events.PLAYER_ANSWERED``
    both refuse — see ``backend/CLAUDE.md``'s "matches" section. Identity
    carries none of that risk: who you're playing was never the secret, only
    how they're doing.
    """

    player = PlayerSerializer()


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
            context=self.context,
        ).data
