"""The whole game, as rows.

``Matchup`` → ``MatchupQuestion`` → ``PlayerAnswer`` is what happened; nothing
here decides what *should* happen — that is ``apps.matches.services``, kept
callable from a test with no socket in sight (see ``backend/CLAUDE.md``).

``MatchupQuestion`` stores ``(question_type, question_id)`` — the
``QuestionRef`` pair ``apps.questions.selectors`` already returns — rather than
a foreign key into one of the seven question tables. That is what keeps this
app independent of every answer shape, and it is why a question is
deactivated rather than deleted: a matchup that already played it points at
that row forever, including one nobody may be served again.
"""

from __future__ import annotations

from django.db import models

from apps.core_common.models import BaseModel
from apps.matches.constants import PLAYERS_PER_MATCHUP


class Matchup(BaseModel):
    """One race between two players, in one category."""

    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Outcome(models.TextChoices):
        #: Set only once the matchup reaches a terminal status, so a live
        #: matchup's outcome is neither of these — see the constraint below.
        PLAYED = "played", "Played to completion"
        ABANDONED = "abandoned", "A player left mid-match"

    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.PROTECT,
        related_name="matchups",
    )

    #: Drawn once from ``constants.MATCH_QUESTION_COUNTS`` when the matchup is
    #: created, and never changed after — the number of ``MatchupQuestion``
    #: rows a completed matchup must have.
    question_count = models.PositiveSmallIntegerField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.WAITING,
    )

    #: Blank until the matchup reaches ``COMPLETED``. Read by
    #: ``services.abandon_matchup`` as well as ``complete_matchup`` — the two
    #: ways a matchup finishes — so a caller can tell "the players finished
    #: it" from "someone left" without inferring it from which rows exist.
    outcome = models.CharField(
        max_length=20,
        choices=Outcome.choices,
        blank=True,
    )

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(status="completed", completed_at__isnull=False)
                    | ~models.Q(status="completed")
                ),
                name="matches_matchup_completed_has_completed_at",
            ),
        ]

    def __str__(self) -> str:
        return f"Matchup {self.pk} ({self.category.slug}, {self.status})"


class MatchupPlayer(BaseModel):
    """One side of a matchup: the running score, and how it ended for them."""

    matchup = models.ForeignKey(
        Matchup,
        on_delete=models.CASCADE,
        related_name="players",
    )

    #: ``PROTECT``, the way ``PlayerAnswer.player`` is: a matchup is a thing
    #: two people did, and removing one of them must not edit the other's
    #: history (the same reasoning as ``Player.user``'s ``SET_NULL``, one
    #: level up — see ``apps.players.models``).
    player = models.ForeignKey(
        "players.Player",
        on_delete=models.PROTECT,
        related_name="matchups",
    )

    score = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    total_answer_time_ms = models.PositiveBigIntegerField(default=0)
    is_winner = models.BooleanField(default=False)

    #: Set by ``services.abandon_matchup``. ``NULL`` for the player who did
    #: not leave, and for every player of a matchup that simply finished.
    left_at = models.DateTimeField(null=True, blank=True)

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta(BaseModel.Meta):
        constraints = [
            # A matchup must contain exactly one row per player — the DB half
            # of "exactly two players", the other half being the count check
            # `services.create_matchup` runs before it writes either row.
            models.UniqueConstraint(
                fields=["matchup", "player"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_matchup_player",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.player.display_name} in matchup {self.matchup_id}"


class MatchupQuestion(models.Model):
    """One question of one matchup, in the order it was drawn.

    Not a ``BaseModel``: it has no independent existence outside the matchup
    that owns it, the way a question row does — soft-deleting one only ever
    happens by soft-deleting the ``Matchup`` it cascades from.
    """

    matchup = models.ForeignKey(
        Matchup,
        on_delete=models.CASCADE,
        related_name="questions",
    )

    #: The pair that identifies the concrete question — see the module
    #: docstring. ``question_id`` is a string because ``core_common.BaseModel``
    #: keys every question table with a UUID.
    question_id = models.CharField(max_length=64)
    question_type = models.CharField(max_length=50)

    #: 1-indexed position in the match, the order the server drew it in.
    order = models.PositiveSmallIntegerField()

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("matchup", "order")
        constraints = [
            models.UniqueConstraint(
                fields=["matchup", "order"], name="uniq_matchup_question_order"
            ),
            # The same question cannot be drawn twice into one matchup —
            # `selectors.select_questions` already guarantees this by sampling
            # without replacement, this is the row-level backstop.
            models.UniqueConstraint(
                fields=["matchup", "question_type", "question_id"],
                name="uniq_matchup_question_ref",
            ),
        ]

    def __str__(self) -> str:
        return f"Q{self.order} of matchup {self.matchup_id} ({self.question_type})"


class PlayerAnswer(models.Model):
    """One player's submission to one question. Not a ``BaseModel`` for the
    same reason ``MatchupQuestion`` is not — it lives and dies with its match.
    """

    matchup_question = models.ForeignKey(
        MatchupQuestion,
        on_delete=models.CASCADE,
        related_name="answers",
    )

    player = models.ForeignKey(
        "players.Player",
        on_delete=models.PROTECT,
        related_name="answers",
    )

    #: The submission exactly as evaluated — e.g. ``{"option_id": "..."}`` —
    #: never a payload the client also stamped a time onto: the server never
    #: reads a client-submitted time (see ``services.submit_answer``).
    answer = models.JSONField()

    is_correct = models.BooleanField()

    #: Credit, 0.0–1.0 — ``AnswerResult.score``. Carried alongside
    #: ``is_correct`` for the one shape where they disagree (a matrix), so a
    #: box score can show partial credit rather than a single tick or cross.
    score = models.FloatField()

    #: What ``constants.score_answer`` paid for this answer — correctness and
    #: speed already combined, the number a scoreboard adds up.
    points = models.PositiveIntegerField()

    #: ``T1 - T0``, both timestamps the server's own
    #: (``MatchupQuestion.started_at`` and the moment this row is written) —
    #: never a duration the client sent. Clamped to the question's time limit.
    response_time_ms = models.PositiveBigIntegerField()

    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # One answer per player per question — the DB half of
            # `submit_answer`'s idempotency (a flaky retry finds this row
            # rather than racing to insert a second one).
            models.UniqueConstraint(
                fields=["matchup_question", "player"],
                name="uniq_player_answer_per_question",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.player.display_name}'s answer to {self.matchup_question_id}"


assert PLAYERS_PER_MATCHUP == 2, (
    "MatchupPlayer's model and constraints assume exactly two sides; a "
    "different value here needs a matching change to both."
)


class BotProfile(BaseModel):
    """How one CPU opponent plays: how often it is right, and how long it
    takes to answer. One row per bot ``Player`` (``player.is_bot=True``),
    authored by ``manage.py seed_bots`` rather than a resource file — a bot
    profile is game-balance data, not content, and there are only 50 of them.

    ``apps.matches.bots.controller`` is the only reader: it draws one
    ``(correct?, delay)`` decision per question from these two numbers.
    Nothing in ``apps.questions`` or ``apps.rankings`` knows a bot is
    different from any other player — the same reason ``Player.is_bot`` is a
    plain flag on an ordinary row rather than a second player table.
    """

    player = models.OneToOneField(
        "players.Player",
        on_delete=models.CASCADE,
        related_name="bot_profile",
    )

    #: Probability, per question, that the bot's submission is deliberately
    #: built correct (``apps.matches.bots.answering.build_bot_answer``). 0.30
    #: to 0.90 across the seeded roster — a bot is never a guaranteed win or a
    #: guaranteed loss for the human it is standing in for.
    accuracy = models.FloatField()

    #: The band its response time is drawn uniformly from, in milliseconds —
    #: server-measured the same way a human's is (``constants.score_answer``
    #: never learns the difference). The seeded roster spans "under 2s" to
    #: "over 9s" end to end; one bot's own band is narrower, which is what
    #: makes it recognisably fast or slow rather than merely random.
    min_response_ms = models.PositiveIntegerField()
    max_response_ms = models.PositiveIntegerField()

    class Meta(BaseModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=models.Q(accuracy__gte=0.0) & models.Q(accuracy__lte=1.0),
                name="bot_profile_accuracy_in_range",
            ),
            models.CheckConstraint(
                condition=models.Q(max_response_ms__gte=models.F("min_response_ms")),
                name="bot_profile_response_band_ordered",
            ),
        ]

    def __str__(self) -> str:
        return f"Bot profile for {self.player.display_name} ({self.accuracy:.0%} accurate)"
