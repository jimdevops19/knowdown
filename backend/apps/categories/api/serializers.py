from __future__ import annotations

from rest_framework import serializers

from apps.categories.models import Category


class CategorySerializer(serializers.ModelSerializer):
    """A category as a client sees it.

    ``id`` is deliberately absent: the slug is the identifier the API takes and
    answers with, so exposing a second one invites clients to key on the UUID
    and then break when a category is reloaded from the resource files.
    """

    class Meta:
        model = Category
        fields = ("slug", "name", "description")
        read_only_fields = fields
