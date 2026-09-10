"""A badge, and who has earned it.

Achievements stay separate from rankings on purpose: a rating says how good a
player is *right now* and can fall; a badge, once earned, is a fact about their
history and never is taken back. ``Achievement`` is the catalog — authored the
same way a question is, in a resource file loaded by a command
(``resources/achievements.yaml``, ``manage.py sync_achievements``) — and
``PlayerAchievement`` is the join recording who has one and when.
"""

from __future__ import annotations

from django.db import models

from apps.core_common.models import BaseModel, SluggedModel


class Achievement(SluggedModel, BaseModel):
    """One badge in the catalog."""

    name = models.CharField(max_length=100)

    #: The stable key ``services.evaluation.ACHIEVEMENT_RULES`` looks a badge
    #: up by, and what ``resources/achievements.yaml`` upserts on — the same
    #: role a question's ``slug`` plays in ``apps.questions``.
    slug = models.SlugField(max_length=100, unique=True)

    description = models.TextField()

    icon = models.ImageField(upload_to="achievements/", null=True, blank=True)

    #: Off means "cannot be newly earned" — a badge retired or still being
    #: authored. Never a delete: a player who already has it keeps it
    #: (``PlayerAchievement`` isn't cascaded from this being switched off),
    #: the same reasoning as a deactivated category or question.
    is_active = models.BooleanField(default=True)

    class Meta(BaseModel.Meta):
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class PlayerAchievement(models.Model):
    """One player having earned one badge. No independent existence beyond
    that pair — the same reasoning as ``apps.matches.models.PlayerAnswer`` —
    so it is a plain ``models.Model``, not a ``BaseModel``."""

    player = models.ForeignKey(
        "players.Player",
        on_delete=models.CASCADE,
        related_name="achievements",
    )

    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name="players",
    )

    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-earned_at",)
        constraints = [
            # The DB half of ``services.evaluation``'s idempotency: awarding
            # is a ``get_or_create`` against this, so a replayed match
            # completion cannot grant the same badge twice.
            models.UniqueConstraint(
                fields=["player", "achievement"], name="unique_player_achievement"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.player.display_name} earned {self.achievement.slug}"
