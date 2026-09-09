"""Thin views: parse input → call one selector → serialize.

There is no write side here. Categories come from ``categories.yaml`` via
``manage.py sync_questions``, which is the whole point of keeping them in a
resource file — the set of sports the product covers is a decision made in a
pull request, not through an endpoint.
"""

from __future__ import annotations

from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from apps.categories.api.serializers import CategorySerializer
from apps.categories.selectors import active_categories


class CategoryListView(ListAPIView):
    """``GET /api/v1/categories/`` — the sports a player can be quizzed on.

    ``AllowAny``: what the product covers is the pitch, and there is no honest
    answer to "what would I be signing up for" that is not this list.
    """

    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    pagination_class = None  # A handful of rows; a page boundary would be noise.

    def get_queryset(self):
        return active_categories()


class CategoryDetailView(RetrieveAPIView):
    """``GET /api/v1/categories/{slug}/``."""

    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    lookup_field = "slug"

    def get_queryset(self):
        return active_categories()
