"""The category endpoints, and the envelope they answer through."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.categories.models import Category
from apps.categories.selectors import active_categories, get_category_by_slug
from apps.core_common.exceptions import NotFound


class CategorySelectorTests(TestCase):
    def setUp(self) -> None:
        self.nba = Category.objects.create(name="NBA", slug="nba")
        self.f1 = Category.objects.create(name="F1", slug="f1", is_active=False)

    def test_active_categories_excludes_the_inactive(self) -> None:
        self.assertEqual([c.slug for c in active_categories()], ["nba"])

    def test_lookup_by_slug_refuses_an_inactive_one(self) -> None:
        with self.assertRaises(NotFound):
            get_category_by_slug(slug="f1")

    def test_the_loader_can_still_find_an_inactive_one(self) -> None:
        self.assertEqual(
            get_category_by_slug(slug="f1", include_inactive=True).pk, self.f1.pk
        )


class CategoryAPITests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        Category.objects.create(name="NBA", slug="nba", description="Basketball.")
        Category.objects.create(name="F1", slug="f1", is_active=False)

    def test_list_is_open_and_hides_inactive_categories(self) -> None:
        response = self.client.get("/api/v1/categories/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"data": [{"slug": "nba", "name": "NBA", "description": "Basketball."}]},
        )

    def test_detail_answers_by_slug(self) -> None:
        response = self.client.get("/api/v1/categories/nba/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["name"], "NBA")

    def test_detail_of_an_inactive_category_is_a_404_envelope(self) -> None:
        response = self.client.get("/api/v1/categories/f1/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")
