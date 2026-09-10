"""Thin views: parse input → call one selector → serialize.

There is no write side here. A rating moves from one place —
``apps.rankings.services.update_ratings_for_matchup``, called off a matchup
completing — never from a request.
"""

from __future__ import annotations

from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from apps.categories.selectors import get_category_by_slug
from apps.rankings import selectors

from .serializers import LadderEntrySerializer


class CategoryLadderView(ListAPIView):
    """``GET /api/v1/rankings/{category}/`` — the standings, best rating
    first. Paginated by ``apps.core_common.pagination.DefaultPagination`` like
    every other list in the API, so a ladder large enough to matter never
    arrives as one response.

    ``AllowAny``: a leaderboard is the pitch the same way the category list
    is (``apps.categories.api.views.CategoryListView``) — there is no honest
    version of this that hides the standings from someone deciding whether to
    play.
    """

    permission_classes = [AllowAny]
    serializer_class = LadderEntrySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no kwargs
            from apps.rankings.models import Ranking

            return Ranking.objects.none()
        category = get_category_by_slug(slug=self.kwargs["category_slug"])
        return selectors.ladder(category=category)
