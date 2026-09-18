"""Whether a player has already faced a question, and how many times.

Exists so ``apps.matches.services.select_match_questions`` can keep a
matchup's board from repeating a question either player has already seen,
without this app needing to know anything about a question beyond the
``(question_type, question_id)`` pair ``apps.questions.selectors.QuestionRef``
already returns — the same decoupling ``matches.MatchupQuestion`` keeps, and
for the same reason: this table must survive a question type it has never
heard of, and a question row that is later deactivated or deleted.
"""

from __future__ import annotations

from django.db import models


class QuestionExposure(models.Model):
    """One player, one question, how many times it has been drawn for them.

    Not a ``core_common.BaseModel``: this is a running count with no
    independent history of its own to soft-delete — removing the player is
    the only thing that should take a row with it.
    """

    player = models.ForeignKey(
        "players.Player",
        on_delete=models.CASCADE,
        related_name="question_exposures",
    )
    question_type = models.CharField(max_length=50)
    question_id = models.CharField(max_length=64)

    #: Starts at 1 — a row is only ever created because a player just saw
    #: this question for the first time — and is bumped by
    #: ``services.record_exposures`` each later matchup that draws it for
    #: them again.
    times_seen = models.PositiveSmallIntegerField(default=1)

    #: Updated on every bump, so "which of these has this player seen least
    #: recently" is answerable without a second table.
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "question_type", "question_id"],
                name="uniq_player_question_exposure",
            ),
        ]
        indexes = [
            # Backs "which (player, question) pairs have been shown more
            # than once" — the query a repeat-exposure alert runs — without
            # a full scan across every player.
            models.Index(fields=["times_seen"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.player.display_name} x{self.times_seen} on "
            f"{self.question_type}:{self.question_id}"
        )
