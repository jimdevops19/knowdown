"""What the rehearsal room says about a question.

Three shapes, and the split between them is the whole design of this module:

- a **card** (:class:`CatalogCardSerializer`) — the metadata a maintainer scans
  a list by, and the half of a question the play-time board deliberately drops:
  its slug, its tags, whether it is still active.
- a **rehearsal** (:func:`serialize_rehearsal`) — the card, plus the exact board
  ``apps.matches`` would put on screen, plus the clock it would run.
- a **verdict** (:class:`VerdictSerializer` and the view that fills it) — what
  the evaluator said, what the scoring curve would have paid, and what the
  answer actually was.

**The board is never re-derived here.** It comes from
``apps.questions.api.serializers.serialize_for_play`` and the key from
``apps.questions.api.reveal.serialize_answer_key`` — the same two functions a
live match and a box score call. A tester that built its own payload would be a
tester that can pass while the real thing is broken, which is the one failure
mode a debugging tool may not have. Everything this module adds sits *beside*
that board, in its own keys, so what a maintainer is looking at is byte for byte
what a player would be looking at.

**Where it does say more than a player is told, it says so out loud.** The card
carries the slug (a slug is sometimes the answer — see
``_QuestionPlaySerializer``), and a gradual-hints rehearsal carries every clue
up front with the offset each is due at. Both are deliberate: this surface is
only ever reached by a staff account on a tier that asked for it, and a
rehearsal that withheld the clues would be unable to rehearse the one question
type whose clues *are* the question.
"""

from __future__ import annotations

from rest_framework import serializers

__all__ = [
    "AnswerAttemptSerializer",
    "CatalogCardSerializer",
    "TesterConfigSerializer",
]


class CatalogCardSerializer(serializers.Serializer):
    """One question as the catalog lists it.

    A plain ``Serializer`` with an explicit field list rather than a
    ``ModelSerializer``, for the reason the play-time module gives at length: a
    ``ModelSerializer`` grows a field when a model grows a column. The stakes
    are lower here — a maintainer is allowed to see an answer — but eight
    question models share this one serializer, and a ``ModelSerializer`` cannot
    be written against eight models anyway.
    """

    id = serializers.UUIDField(read_only=True)
    #: The discriminator everything downstream switches on, and the first half
    #: of the ``(type, id)`` pair that names a question in this platform.
    type = serializers.CharField(source="question_type", read_only=True)
    #: Present here and absent from every play-time payload. The slug is how a
    #: question is named in YAML, in a bug report and in `sync_questions` output
    #: — which is exactly what somebody looking for "the one about Kobe's 81"
    #: needs, and exactly what a player must not be handed.
    slug = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    level = serializers.IntegerField(read_only=True)
    category = serializers.CharField(source="category.slug", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    tags = serializers.DictField(read_only=True)
    #: Worth a badge on the card: a deactivated question is invisible to
    #: matchmaking, and "why does this never come up" is one of the two or three
    #: things this page exists to answer.
    is_active = serializers.BooleanField(read_only=True)
    #: The author's override in seconds, or null for "whatever the type's
    #: default is". Null is meaningful, so it is sent rather than resolved —
    #: the resolved figure rides on the rehearsal payload as `time_limit_ms`.
    time_limit_seconds = serializers.IntegerField(read_only=True, allow_null=True)
    image = serializers.SerializerMethodField()

    def get_image(self, question) -> str | None:
        return question.image.url if question.image else None


class TesterConfigSerializer(serializers.Serializer):
    """What the tester page needs before it can draw its filter bar."""

    enabled = serializers.BooleanField(read_only=True)
    question_count = serializers.IntegerField(read_only=True)
    categories = serializers.ListField(child=serializers.DictField(), read_only=True)
    types = serializers.ListField(child=serializers.DictField(), read_only=True)
    #: The difficulty bands, each carrying the ``level_min``/``level_max`` pair
    #: that filters the catalog by it — see :class:`TesterConfigView`.
    levels = serializers.ListField(child=serializers.DictField(), read_only=True)


class AnswerAttemptSerializer(serializers.Serializer):
    """A rehearsed answer: the payload, and how long it was pretended to take.

    ``submitted`` is passed through untouched to
    ``apps.questions.services.evaluation.evaluate_answer``, which is what
    validates it — this serializer deliberately does not know the eight answer
    shapes. Anything malformed comes back as the same ``malformed_answer``
    refusal a live socket would send, which is a thing worth being able to
    provoke on purpose from here.

    ``elapsed_ms`` is the one place this app does something the real platform
    refuses to do: **it takes the client's word for the clock.** ``submit_answer``
    measures speed against the server's own stamp and would reject a figure sent
    from a browser, because speed is scored and a scored number may not be
    self-reported. Here nothing is at stake — no matchup, no points that persist,
    no ladder — and being able to ask "what would this have paid at four
    seconds?" without sitting there for four seconds is most of the value of a
    rehearsal. It is clamped to the question's own limit by the view, so the
    answer to "what does it pay at minus one second" is not an interesting one.
    """

    submitted = serializers.DictField()
    elapsed_ms = serializers.IntegerField(required=False, min_value=0)
