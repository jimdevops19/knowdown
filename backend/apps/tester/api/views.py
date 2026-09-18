"""The rehearsal room's four endpoints.

Thin, in the way every view in this backend is thin: parse input, call one
selector or one service, serialize. The only thing here that is not a pass-
through is :class:`AnswerAttemptView`'s clamp on the rehearsed clock, and that
is three lines with a comment on them.

**Every one of these carries the same two gates.** ``IsMaintainer`` on each
view, and the whole module unmounted by ``TESTER_ENDPOINT_ENABLED`` — see
``config/urls.py``. They are repeated per view rather than left to a base class
so that adding a fifth endpoint by copying a fourth cannot quietly produce an
open one.

**Nothing here writes.** No ``Matchup``, no ``PlayerAnswer``, no rating: a
rehearsal is a read of the catalog plus a pure function over what was typed, so
there is no ``services/`` layer in this app and no transaction to wrap.
"""

from __future__ import annotations

from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core_common.exceptions import ValidationFailed
from apps.matches.constants import (
    QUESTION_READ_DELAY_MS,
    score_answer,
    time_limit_ms_for,
)
from apps.questions.api.reveal import serialize_answer_key
from apps.questions.api.serializers import serialize_for_play
from apps.questions.constants import LEVEL_BANDS
from apps.questions.models import MAX_LEVEL, QUESTION_MODELS, QuestionType
from apps.questions.selectors import QuestionRef, get_question, reveal_schedule
from apps.questions.services.evaluation import evaluate_answer
from apps.tester import selectors
from apps.tester.api.serializers import (
    AnswerAttemptSerializer,
    CatalogCardSerializer,
    TesterConfigSerializer,
)
from apps.tester.permissions import IsMaintainer
from shared.logging import get_logger, labels

logger = get_logger(__name__)

#: The default board order for a rehearsal. ``serialize_for_play`` wants a
#: matchup id because in a real game the shuffle is a function of the matchup
#: (``shuffle_seed``) — two players must read the same board. There is no
#: matchup here, so the caller supplies a seed instead and this is what they get
#: if they don't: a constant, so that reloading the page does not reshuffle the
#: options under somebody who is halfway through reading them. Passing
#: ``?seed=`` anything else is how a maintainer asks to see it dealt again,
#: which is the only honest way to check that an ordering question is not
#: secretly answerable from its authored order.
DEFAULT_SHUFFLE_SEED = "tester"


def _parse_level_range(request) -> tuple[int, int] | None:
    """``?level_min=&level_max=`` as the pair the selector takes, or nothing."""
    raw_min = request.query_params.get("level_min")
    raw_max = request.query_params.get("level_max")
    if raw_min is None and raw_max is None:
        return None
    try:
        low = int(raw_min) if raw_min is not None else 1
        high = int(raw_max) if raw_max is not None else MAX_LEVEL
    except ValueError as exc:
        raise ValidationFailed("level_min and level_max must be whole numbers.") from exc
    if low > high:
        raise ValidationFailed("level_min may not be greater than level_max.")
    return (low, high)


class TesterConfigView(APIView):
    """``GET /api/v1/tester/config/`` — what the page needs to draw itself.

    The filter bar's vocabulary (which categories hold questions, how many of
    each type and each difficulty band there are) plus a flat ``enabled: true``. The flag is stated in
    the body even though reaching this view at all already proves it: the client
    asks this one endpoint to decide whether to show the tester at all, and
    "200 means yes" is a contract that reads as an accident. A tier with the
    tester off answers **404**, because the route is not mounted — which is the
    same answer the client treats as "no", and the reason it probes rather than
    assuming.
    """

    permission_classes = [IsMaintainer]

    @extend_schema(tags=["tester"], responses=TesterConfigSerializer)
    def get(self, request, *args, **kwargs) -> Response:
        counts = selectors.catalog_counts()
        return Response(
            TesterConfigSerializer(
                {
                    "enabled": settings.TESTER_ENDPOINT_ENABLED,
                    "question_count": counts.total,
                    "categories": [
                        {"slug": slug, "name": name, "question_count": count}
                        for slug, (name, count) in sorted(
                            counts.categories.items(), key=lambda item: item[1][0]
                        )
                    ],
                    # Every type, including the ones at zero — see
                    # `CatalogCounts`. Ordered by the enum rather than by count,
                    # so the filter bar does not reorder itself as the catalog
                    # grows.
                    "types": [
                        {
                            "value": value,
                            "label": str(QuestionType(value).label),
                            "question_count": counts.types.get(value, 0),
                        }
                        for value in QUESTION_MODELS
                    ],
                    # The same three bands the matchmaker draws from, sent with
                    # the level range each covers rather than only its name:
                    # the filter is `level_min`/`level_max` on the list
                    # endpoint, so a client that only knew the word "medium"
                    # would have to hardcode 4..7 to use it — and re-cutting a
                    # band is meant to be one edit to `LEVEL_BANDS`.
                    "levels": [
                        {
                            "value": band.name,
                            "label": band.name.title(),
                            "level_min": band.low,
                            "level_max": band.high,
                            "question_count": counts.levels.get(band.name, 0),
                        }
                        for band in LEVEL_BANDS
                    ],
                }
            ).data
        )


class CatalogListView(ListAPIView):
    """``GET /api/v1/tester/questions/`` — the catalog, searchable.

    Filters: ``search``, ``category``, ``type``, ``level_min``/``level_max``,
    and ``include_inactive`` (**on** by default — see the selector module for
    why this surface's default is the opposite of the match engine's).

    ``filter_backends`` is emptied because there is no queryset to filter: a
    question is eight tables and this list is assembled in Python
    (``selectors.search_questions``). DRF's paginator is happy with a list, its
    filter backends are not, and the default backends would otherwise raise on
    the first request rather than at import.
    """

    permission_classes = [IsMaintainer]
    serializer_class = CatalogCardSerializer
    filter_backends = ()

    @extend_schema(
        tags=["tester"],
        parameters=[
            OpenApiParameter("search", str, description="Matches slug, text or category name."),
            OpenApiParameter("category", str, description="Category slug."),
            OpenApiParameter("type", str, description="A QuestionType value."),
            OpenApiParameter("level_min", int),
            OpenApiParameter("level_max", int),
            OpenApiParameter(
                "include_inactive",
                bool,
                description="Default true — a deactivated question is often the one being debugged.",
            ),
        ],
        responses=CatalogCardSerializer(many=True),
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        request = self.request
        include_inactive = request.query_params.get("include_inactive", "true")
        return selectors.search_questions(
            search=request.query_params.get("search"),
            category_slug=request.query_params.get("category"),
            question_type=request.query_params.get("type"),
            level_range=_parse_level_range(request),
            include_inactive=include_inactive.strip().lower() not in {"0", "false", "no"},
        )


class _QuestionView(APIView):
    """Shared by the two endpoints that name one question in the URL."""

    permission_classes = [IsMaintainer]

    def question(self):
        """The row ``(type, id)`` points at, or a 404 from ``get_question``.

        Deliberately the same selector the match engine and the box score use,
        including its indifference to ``is_active``: a retired question is
        precisely the one somebody is here to look at.
        """
        return get_question(
            ref=QuestionRef(self.kwargs["question_type"], str(self.kwargs["question_id"]))
        )


class RehearsalView(_QuestionView):
    """``GET /api/v1/tester/questions/{type}/{id}/`` — one question, as played.

    The response is a card, the **real** play-time board, and the clock a
    matchup would run on it — enough for a client to stage the question exactly
    as `MatchPage` does: hold the options back for the read delay, count down
    from `time_limit_ms`, then lock.

    ``hints`` is the deliberate exception, and the only one. For every type but
    gradual-hints it is empty. For that one it carries the full schedule —
    each clue and the offset it is due at — which is text a live board must
    never hold (``FORBIDDEN_FIELD_NAMES`` bans ``hints`` by name, and the socket
    pays them out frame by frame precisely so that waiting is what buys them).
    Here there is no socket to pay them out and no opponent to beat to them, and
    a rehearsal that could not show a gradual-hints question is a rehearsal with
    a hole in it exactly where the most fragile question type is. The client
    replays the schedule against its own clock; the payload says when, not just
    what.
    """

    @extend_schema(
        tags=["tester"],
        parameters=[
            OpenApiParameter(
                "seed",
                str,
                description="Board order. Change it to deal the same question again.",
            )
        ],
        responses=None,
    )
    def get(self, request, *args, **kwargs) -> Response:
        question = self.question()
        seed = request.query_params.get("seed") or DEFAULT_SHUFFLE_SEED

        return Response(
            {
                **CatalogCardSerializer(question).data,
                "seed": seed,
                # The same two numbers the match engine would use, from the same
                # function — not a copy of its defaults. A question whose
                # authored `time_limit_seconds` is wrong should be wrong here in
                # the same way it would be in a match.
                "time_limit_ms": time_limit_ms_for(
                    question_type=question.question_type,
                    override_seconds=question.time_limit_seconds,
                ),
                "read_delay_ms": QUESTION_READ_DELAY_MS,
                "board": serialize_for_play(question=question, matchup_id=seed),
                "hints": [
                    {"index": step.index, "text": step.text, "offset_ms": step.offset_ms}
                    for step in reveal_schedule(question=question)
                ],
            }
        )


class AnswerAttemptView(_QuestionView):
    """``POST /api/v1/tester/questions/{type}/{id}/answer/`` — mark my answer.

    Body: ``{"submitted": {...}, "elapsed_ms": 4200}``. The submission is the
    identical payload a live socket takes, refused in the identical way if it is
    malformed, and scored by the identical evaluator — so a question that grades
    surprisingly here grades surprisingly in a match, which is the point.

    The response says three things, and they are three rather than one because
    they can disagree and the disagreement is usually the bug:

    - ``is_correct`` / ``score`` — the verdict and the credit. A matrix with one
      cell wrong is ``false`` and ``0.89``, and a tool that reported only the
      boolean would hide the most common thing worth knowing about a grid.
    - ``points`` — what that credit would have paid at ``elapsed_ms``, through
      ``matches.constants.score_answer``, the same curve a real match pays on.
    - ``answer_key`` — what was actually right, from
      ``apps.questions.api.reveal``. Sent on every attempt, right or wrong,
      because the question a maintainer is here to answer is "what did it want?"
      and making that a second request would mean half the answers never get
      looked at.
    """

    @extend_schema(tags=["tester"], request=AnswerAttemptSerializer, responses=None)
    def post(self, request, *args, **kwargs) -> Response:
        question = self.question()
        attempt = AnswerAttemptSerializer(data=request.data)
        attempt.is_valid(raise_exception=True)
        submitted = attempt.validated_data["submitted"]

        time_limit_ms = time_limit_ms_for(
            question_type=question.question_type,
            override_seconds=question.time_limit_seconds,
        )
        # Clamped the way `services.submit_answer` clamps its own measurement,
        # so the curve is asked the same question it is asked in a match. An
        # absent `elapsed_ms` is treated as an instant answer: the common case
        # is a maintainer checking whether an answer is *accepted*, and making
        # them state a time first would be a required field for a rehearsal.
        elapsed_ms = min(attempt.validated_data.get("elapsed_ms", 0), time_limit_ms)

        result = evaluate_answer(question=question, submitted=submitted)
        points = score_answer(
            credit=result.score,
            response_time_ms=elapsed_ms,
            time_limit_ms=time_limit_ms,
        )

        # One line per rehearsed answer. `question` and `question_type` are on
        # the log schema as labels, so this reads without a database beside it —
        # and it is the only trace a rehearsal leaves anywhere, which is worth
        # having for a surface that reveals answer keys.
        logger.info(
            "Question rehearsed",
            action="tester.answer",
            user=labels.user(request.user),
            question=labels.question(question),
            question_type=question.question_type,
        )

        return Response(
            {
                "is_correct": result.is_correct,
                "score": result.score,
                "points": points,
                "elapsed_ms": elapsed_ms,
                "time_limit_ms": time_limit_ms,
                "submitted": submitted,
                "answer_key": serialize_answer_key(
                    question=question, submitted=submitted
                ),
            }
        )


class AnswerKeyView(_QuestionView):
    """``GET /api/v1/tester/questions/{type}/{id}/answer-key/`` — just tell me.

    The same key :class:`AnswerAttemptView` returns, without answering first.
    Separate rather than a flag on the rehearsal payload, because the rehearsal
    is the thing you are meant to *play* — a board that arrived with its key
    attached would make every attempt at it a formality, including the honest
    ones. Asking for the answer is a different request, and it looks like one.

    ``submitted`` is ``None`` here, so a truncated pool comes back in its
    authored order (most obvious first) rather than floated around anybody's
    answer — there isn't one.
    """

    @extend_schema(tags=["tester"], responses=None)
    def get(self, request, *args, **kwargs) -> Response:
        question = self.question()
        return Response(serialize_answer_key(question=question, submitted=None))
