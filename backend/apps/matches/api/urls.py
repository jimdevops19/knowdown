"""Match history routes. Nothing here starts or scores a match — that is the
socket transport Phase D adds; this app answers only "what happened"."""

from __future__ import annotations

from django.urls import path

from .views import MatchHistoryDetailView, MatchHistoryListView

app_name = "matches"

urlpatterns = [
    path("", MatchHistoryListView.as_view(), name="list"),
    path("<uuid:matchup_id>/", MatchHistoryDetailView.as_view(), name="detail"),
]
