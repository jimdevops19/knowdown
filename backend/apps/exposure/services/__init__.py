"""Write side: recording that a player has now seen a question."""

from __future__ import annotations

from django.db import transaction
from django.db.models import F

from apps.exposure.models import QuestionExposure

__all__ = ["record_exposures"]


@transaction.atomic
def record_exposures(*, player_ids, refs) -> None:
    """One row per (player, question) ever drawn; bumps ``times_seen`` on a
    repeat rather than inserting a second row.

    Called once per matchup, right after its board is fixed
    (``apps.matches.services.select_match_questions``), for both players and
    every question drawn — the only writer, so this count can never drift
    from "how many times this pair has actually been dealt this question."
    """
    for player_id in player_ids:
        for ref in refs:
            existing = QuestionExposure.objects.filter(
                player_id=player_id,
                question_type=ref.question_type,
                question_id=ref.question_id,
            ).first()
            if existing is None:
                QuestionExposure.objects.create(
                    player_id=player_id,
                    question_type=ref.question_type,
                    question_id=ref.question_id,
                )
            else:
                existing.times_seen = F("times_seen") + 1
                existing.save(update_fields=["times_seen", "last_seen_at"])
