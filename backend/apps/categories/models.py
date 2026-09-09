"""What a question is *about*, kept apart from how it is answered.

A category is the subject — NBA today, Premier League, F1, UFC later. The
question models in ``apps.questions`` describe the *shape* of an answer, and the
two axes never meet: adding a sport is adding a row here plus a folder of YAML,
not a new question type, and adding a question type does not touch this table.
That separation is what lets one game engine eventually power several titles.

A category is also the scope of a ranking (``apps.rankings``): a player has an
NBA rating and an F1 rating, not one number spanning both.
"""

from __future__ import annotations

from django.db import models

from apps.core_common.models import BaseModel, SluggedModel


class Category(SluggedModel, BaseModel):
    """A subject questions belong to.

    ``slug`` is the identifier everything else names it by — the API looks a
    category up by it, and every question resource file opens by naming the
    category its questions belong to — so it is the stable half of the row and
    ``name`` is the display half. ``SluggedModel`` fills it from the name for a
    category created in the admin; a category loaded from ``categories.yaml``
    always states its own.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    #: Off means "do not draw questions from here" — a sport that is out of
    #: season, or one still being authored. Deliberately not a delete: matchups
    #: already played in this category keep pointing at it.
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name
