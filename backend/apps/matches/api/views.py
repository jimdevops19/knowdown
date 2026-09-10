"""Match history: read-only, on purpose.

Scoring happens through ``apps.matches.services`` — over a socket once Phase D
exists — and a REST write path here would be a second implementation of the
same rules. These two views only ever call selectors.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated

from apps.core_common.exceptions import Conflict, PermissionDenied
from apps.matches import selectors
from apps.players.services import ensure_player_for_user

from .serializers import MatchupDetailSerializer, MatchupListSerializer


class MatchHistoryListView(ListAPIView):
    """``GET /api/v1/matches/`` — the caller's own matches, newest first."""

    permission_classes = [IsAuthenticated]
    serializer_class = MatchupListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no request.user
            from apps.matches.models import Matchup

            return Matchup.objects.none()
        player = ensure_player_for_user(user=self.request.user)
        return selectors.list_matchups_for_player(player=player)


class MatchHistoryDetailView(RetrieveAPIView):
    """``GET /api/v1/matches/{id}/`` — the full box score of one **finished** match.

    Two gates, and they refuse different things.

    *Scoped to its two players*: a matchup is a private result between them
    until ``apps.rankings``/``apps.achievements`` (Phase E) make a public
    profile out of what it fed into.

    *And only once it is over.* That second gate is the anti-cheat one, and it
    is needed precisely because the first gate passes: a player in a live match
    knows their own matchup id — it is in the URL of the screen they are on —
    and is a legitimate party to it, so every ownership check here says yes
    while the clock is still running. What they would be handed is the rest of
    the game:

    - **every question, including the ones nobody has been asked yet.** The
      board is answer-free (``serialize_for_play`` guarantees that), but a
      player who can read questions 2 and 3 while answering question 1 has as
      long as they like to work them out, and the whole game is a race.
    - **the opponent's submission, while their own clock runs.** ``answers``
      is keyed by every player who has answered, with ``submitted`` and
      ``is_correct`` beside it. On a single-answer question that pair *is* the
      key. ``events.PLAYER_ANSWERED`` goes to great lengths to say who
      answered and never what they said or whether they were right, for
      exactly this reason; publishing it here over REST gave it away anyway.

    Nothing legitimate is lost. Mid-match state is the socket's job
    (``consumers.MatchupConsumer``) — REST has no part in a live game, and the
    frontend only ever calls this after ``events.MATCH_COMPLETED``.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = MatchupDetailSerializer
    lookup_url_kwarg = "matchup_id"

    @extend_schema(tags=["matches"], responses=MatchupDetailSerializer)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_object(self):
        player = ensure_player_for_user(user=self.request.user)
        matchup = selectors.get_matchup(matchup_id=self.kwargs["matchup_id"])
        if not matchup.players.filter(player=player).exists():
            raise PermissionDenied("This matchup did not involve you.")
        if matchup.status not in selectors.FINISHED_STATUSES:
            # 409, not 403: the caller is the right person and this will be
            # theirs to read shortly. Nothing about *who* is asking is wrong,
            # only *when* — which is what a Conflict says.
            raise Conflict(
                "This matchup is still in progress. Its box score is available once it ends.",
                code="matchup_in_progress",
            )
        return matchup
