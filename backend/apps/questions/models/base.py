"""What every question has, whatever shape its answer takes.

The split this app is built on: a **category** says what a question is about,
a **question type** says how it is answered. Neither knows about the other, so
adding UFC is a folder of YAML and adding a new way to answer is a model here —
and never both.
"""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core_common.models import BaseModel

#: The hardest a question may be. Ten bands rather than easy/medium/hard because
#: the matchmaker will eventually want to pitch a question at a rating, and three
#: buckets are not enough resolution to do that with.
MAX_LEVEL = 10


class QuestionType(models.TextChoices):
    """The answer shapes, and the key each is authored under in YAML.

    The *values* are the ``type:`` keys in the resource files and the discriminator
    on the pydantic union in ``apps.questions.schemas`` — so they are a published
    contract with the people writing questions, not an internal enum. They are
    also what ``matches.MatchupQuestion`` will store beside a question id to say
    which table that id lives in, which is why they must never be renamed once a
    matchup has recorded one.
    """

    SINGLE_ANSWER = "single-answer", "Single answer"
    IMAGE_ANSWER = "image-answer", "Single answer (image options)"
    MULTIPLE_ANSWER = "multiple-answer", "Multiple answers"
    TRUE_FALSE = "true-false", "True / false"
    FREE_TEXT = "free-text", "Free text"
    ORDERING = "ordering", "Ordering"
    MATRIX = "matrix", "Columns and rows"


class BaseQuestion(BaseModel):
    """Fields common to every question, whatever its answer shape.

    Abstract, not a parent table: each question type gets its own table, because
    the *options* differ in kind (a text option, an image option, a cell in a
    grid) and multi-table inheritance would buy one shared primary key at the
    price of a join on every read. What holds the types together instead is
    :data:`~apps.questions.models.QUESTION_MODELS`, the registry that lets the
    loader, the selectors and the admin walk all of them.
    """

    #: The upsert key, and the name a question is known by everywhere outside the
    #: database. A question is authored in YAML and loaded repeatedly: without a
    #: stable key of its own, editing a typo in a question would insert a second
    #: copy of it rather than correct the first. Unique per table by constraint
    #: and unique across *every* question table by the loader — ``MatchupQuestion``
    #: identifies a question by (type, id), and a slug meaning two things is a
    #: question nobody can name in a bug report.
    slug = models.SlugField(max_length=120, unique=True)

    #: The question as the player reads it.
    description = models.TextField()

    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.PROTECT,
        related_name="%(class)ss",
    )

    #: Free-form facets — ``{"subcategory": "nba-history", "era": "2000s"}``.
    #: A dict rather than a Tag table because these are *filters for question
    #: selection*, not entities anyone manages: nothing needs to list every era,
    #: rename one, or hang a row off it. When something does, that is the moment
    #: for a table.
    tags = models.JSONField(default=dict, blank=True)

    level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_LEVEL)],
        help_text=f"Difficulty, 1 (easiest) to {MAX_LEVEL}.",
    )

    #: Illustrates the *question* — a photo of the play being asked about. Not to
    #: be confused with an image-answer question, where the images are the
    #: options (see ``ImageAnswerOption``).
    image = models.ImageField(upload_to="questions/", null=True, blank=True)

    #: Off means "do not serve this to anyone". Set by the loader when a question
    #: disappears from the YAML, because a matchup that already played it keeps
    #: pointing at the row: deleting it would edit a game that has been played.
    is_active = models.BooleanField(default=True)

    #: Overrides how long a matchup leaves this question open, in seconds.
    #: ``None`` — the common case — means "no override": a matchup falls back
    #: to ``apps.matches.constants.time_limit_ms_for``'s per-type default, and
    #: below that, its default of last resort. Authored per question, in YAML,
    #: the same as ``level`` or ``tags`` — this app only carries the number;
    #: deciding what it is *worth* is ``apps.matches``' the same way scoring is
    #: (``backend/CLAUDE.md``).
    time_limit_seconds = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ("slug",)

    def __str__(self) -> str:
        return self.slug

    @property
    def question_type(self) -> str:
        """This row's :class:`QuestionType` value.

        Declared on each concrete model rather than derived from the class name,
        so a model can be renamed without silently changing the string a played
        matchup recorded.
        """
        raise NotImplementedError
