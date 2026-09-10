"""Fan a server decision out to the socket(s) that need to hear it.

The consumers (``consumers.py``) call straight into ``apps.matches.services``
and then call these functions with the result — there is no separate
"publisher process" reading Postgres, because the whole point of Phase C was
that the rules already run synchronously, inside the request that decided
them.

**``publish`` never raises.** A Redis outage must degrade the live view, not
500 a call whose database write already committed — the same rule rpool's
``apps.realtime.publish`` states for the same reason. Every function here
swallows ``OSError`` (the channel layer unreachable/refused) and logs a
warning instead.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from shared.logging import get_logger

from . import events, groups

logger = get_logger(__name__)


def publish_match_found(*, player_id: UUID | str, matchup_id: UUID | str) -> None:
    """Tell one waiting player's socket that a pairing happened."""
    _send_to_player(
        player_id=player_id,
        message={"type": events.MATCH_FOUND, "matchup_id": str(matchup_id)},
    )


def publish_question_started(*, matchup_id: UUID | str, order: int, board: dict) -> None:
    """One question opened. ``board`` is already play-time-serialized
    (``questions.api.serializers.serialize_for_play``) — this module does not
    know a question's shape, only that it must forward whatever it is given."""
    _send_to_matchup(
        matchup_id=matchup_id,
        message={
            "type": events.QUESTION_STARTED,
            "order": order,
            "question": board,
        },
    )


def publish_player_answered(*, matchup_id: UUID | str, order: int, player_id: UUID | str) -> None:
    """One player locked in an answer. Carries no verdict — see
    ``events.PLAYER_ANSWERED``."""
    _send_to_matchup(
        matchup_id=matchup_id,
        message={
            "type": events.PLAYER_ANSWERED,
            "order": order,
            "player_id": str(player_id),
        },
    )


def publish_question_result(*, matchup_id: UUID | str, order: int, results: list[dict]) -> None:
    """The question closed. ``results`` is one dict per player — the only
    message allowed to carry a verdict."""
    _send_to_matchup(
        matchup_id=matchup_id,
        message={
            "type": events.QUESTION_RESULT,
            "order": order,
            "results": results,
        },
    )


def publish_match_completed(*, matchup_id: UUID | str, summary: dict) -> None:
    _send_to_matchup(
        matchup_id=matchup_id,
        message={"type": events.MATCH_COMPLETED, **summary},
    )


def publish_opponent_disconnected(*, matchup_id: UUID | str, player_id: UUID | str) -> None:
    _send_to_matchup(
        matchup_id=matchup_id,
        message={
            "type": events.OPPONENT_DISCONNECTED,
            "player_id": str(player_id),
        },
    )


def publish_opponent_reconnected(*, matchup_id: UUID | str, player_id: UUID | str) -> None:
    _send_to_matchup(
        matchup_id=matchup_id,
        message={
            "type": events.OPPONENT_RECONNECTED,
            "player_id": str(player_id),
        },
    )


def _send_to_matchup(*, matchup_id: UUID | str, message: dict[str, Any]) -> None:
    _send(group=groups.matchup_group(matchup_id), message=message)


def _send_to_player(*, player_id: UUID | str, message: dict[str, Any]) -> None:
    _send(group=groups.player_group(player_id), message=message)


def _send(*, group: str, message: dict[str, Any]) -> None:
    """Hand one message to the channel layer, swallowing transport failures."""
    layer = get_channel_layer()
    if layer is None:  # pragma: no cover - CHANNEL_LAYERS is always configured
        return
    try:
        async_to_sync(layer.group_send)(group, message)
    except OSError as exc:
        # Redis unreachable/refused. Named rather than bare `Exception` so a
        # bug in our own payload still raises loudly in tests.
        logger.warning(
            "Live update dropped — channel layer unreachable",
            action=message.get("type"),
            reason=str(exc),
        )
