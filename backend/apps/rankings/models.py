"""A rating per player, per category.

Rankings are **category-specific** — an NBA rating and an F1 rating are
different numbers about different things, so a player's row here is keyed on
``(player, category)`` rather than holding one global number. See
``apps.categories.models.Category`` for why that scoping lives at the category
rather than anywhere else.

There is no audit trail (no ``RatingChange``-style ledger): every completed
matchup moves a rating exactly once, from ``apps.rankings.services.ratings``,
and nothing here needs to be unwound or replayed.
"""

from __future__ import annotations

from django.db import models

from apps.core_common.models import BaseModel
from apps.matches.constants import DEFAULT_PLAYER_RATING


class Ranking(BaseModel):
    """One player's standing in one category."""

    #: ``CASCADE``: unlike a matchup, a ranking row is current standing, not a
    #: record of something that happened — removing the player leaves nothing
    #: for it to describe.
    player = models.ForeignKey(
        "players.Player",
        on_delete=models.CASCADE,
        related_name="rankings",
    )

    #: ``PROTECT``, the way every other reference to a category is: a category
    #: goes inactive rather than disappearing, so the ladder it scores stays
    #: reachable (``apps.categories.models.Category.is_active``).
    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.PROTECT,
        related_name="rankings",
    )

    rating = models.IntegerField(default=DEFAULT_PLAYER_RATING)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    games_played = models.PositiveIntegerField(default=0)

    class Meta(BaseModel.Meta):
        constraints = [
            # A player has at most one live row per category — the DB half of
            # `services.ensure_ranking`'s get-or-create, the way display-name
            # uniqueness is enforced twice in `apps.players`.
            models.UniqueConstraint(
                fields=["player", "category"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_ranking_player_category",
            ),
        ]
        indexes = [
            # A ladder read is "the top of one category, by rating" — this is
            # the index that query walks in order rather than sorting.
            models.Index(fields=["category", "-rating"]),
        ]

    def __str__(self) -> str:
        return f"{self.player.display_name} @ {self.rating} ({self.category.slug})"
