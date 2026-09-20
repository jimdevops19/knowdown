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
    "QuestionActivationSerializer",
    "QuestionCreateSerializer",
    "QuestionSourceSerializer",
    "QuestionUpdateSerializer",
    "QuestionWriteResultSerializer",
    "SyncReportSerializer",
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
    #: Whether this tier honours the write verbs (QUESTION_TESTER_EDITABLE).
    #: Sent on the call the page already makes, so the editor can arrive
    #: disabled-with-a-reason rather than discovering the 403 on submit — the
    #: refusal itself lives in ``permissions.CanEditQuestions``, and this is
    #: only what lets the client be honest about it in advance.
    editable = serializers.BooleanField(read_only=True)
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


class QuestionSourceSerializer(serializers.Serializer):
    """One question as its resource file has it.

    ``entry`` is the raw YAML mapping, passed through rather than described
    field by field, and that is the whole reason this surface can edit nine
    answer shapes without nine serializers. The shape it must obey is already
    written down once — ``apps.questions.schemas`` — and re-stating it here in
    DRF fields would be a second copy to keep in step with the loader, which is
    the copy that would drift and start accepting files the loader refuses.
    """

    #: ``nba/single-answer.yaml`` — the file to look at in the diff.
    path = serializers.CharField(read_only=True)
    category = serializers.CharField(read_only=True)
    entry = serializers.DictField(read_only=True)


class SyncReportSerializer(serializers.Serializer):
    """What the load that followed the edit did — ``LoadReport``, as JSON.

    Sent back on every write because there are *two* effects and only one of
    them is the one the form was filled in for. A save that wrote the file and
    updated no row means the loader did not see the question it just wrote,
    which is a real failure mode (a file the category's ``_active.yaml`` does
    not list) and one nobody would notice from a green toast.
    """

    created = serializers.ListField(child=serializers.CharField(), read_only=True)
    updated = serializers.ListField(child=serializers.CharField(), read_only=True)
    deactivated = serializers.ListField(child=serializers.CharField(), read_only=True)
    #: The same sentence ``manage.py sync_questions`` prints.
    summary = serializers.CharField(read_only=True)


class QuestionWriteResultSerializer(serializers.Serializer):
    """The answer to a create or an update: both halves of what happened.

    The row (``question``), the file (``source``, plus whether the block was
    written or rewritten), and the load (``sync``). A client that showed only
    the first would be reporting a database change for an operation whose whole
    point is that it is a change to the *resources*.
    """

    question = CatalogCardSerializer(read_only=True)
    source = QuestionSourceSerializer(read_only=True)
    #: ``created`` or ``updated``, about the block in the file.
    action = serializers.CharField(read_only=True)
    sync = SyncReportSerializer(read_only=True)


class QuestionCreateSerializer(serializers.Serializer):
    """``POST /tester/questions/`` — the category to file it under, and the entry.

    The category is separate from the entry because it is not a field of one: a
    resource file states its category once at the top and every question in it
    inherits that, so an entry carrying its own would be a question that could
    disagree with the file it lives in (which the loader refuses by name).
    """

    category = serializers.CharField()
    entry = serializers.DictField()


class QuestionUpdateSerializer(serializers.Serializer):
    """``PUT …/source/`` — the entry, whole.

    A replace rather than a merge, and deliberately so: half the fields on a
    question mean something by their *absence*. Dropping ``time_limit_seconds``
    is how an entry goes back to taking its file's clock, and dropping
    ``image`` is how a picture is removed — neither of which a patch-merge of
    the keys that happened to be sent could ever express.
    """

    entry = serializers.DictField()


class QuestionActivationSerializer(serializers.Serializer):
    """``PATCH …/source/`` — retire a question, or bring it back.

    Its own verb rather than an ``is_active`` in the update body, because it is
    the one edit made *without* opening the form: the catalog list has a switch
    on each row, and making it send back the whole entry would mean a stale list
    could silently revert somebody else's edit to the question it toggled.
    """

    is_active = serializers.BooleanField()
