"""Match history: read-only, on purpose.

Scoring happens through ``apps.matches.services`` — over a socket once Phase D
exists — and a REST write path here would be a second implementation of the
same rules. These two views only ever call selectors.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated

from apps.core_common.exceptions import PermissionDenied
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
    """``GET /api/v1/matches/{id}/`` — the full box score of one match.

    Scoped to its two players: a matchup is a private result between them
    until ``apps.rankings``/``apps.achievements`` (Phase E) make a public
    profile out of what it fed into.
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
        return matchup
