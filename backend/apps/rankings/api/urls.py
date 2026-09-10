"""Ladder routes. Read-only — see ``api/views.py``."""

from __future__ import annotations

from django.urls import path

from .views import CategoryLadderView

app_name = "rankings"

urlpatterns = [
    path("<slug:category_slug>/", CategoryLadderView.as_view(), name="ladder"),
]
