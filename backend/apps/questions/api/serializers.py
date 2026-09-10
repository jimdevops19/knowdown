"""What a player is allowed to see of a question.

**This module is the anti-cheat surface.** A question row holds the answer —
``is_correct`` on an option, ``answer`` on a true/false, ``correct_position`` on
an ordering item, ``answer`` on a matrix cell — and the payload that goes out
over the socket while the clock is running must hold none of it. Everything else
in the platform can be wrong and cost somebody a match; this being wrong ends
the game, because a player who can read the answer out of a network tab does not
need to know any basketball.

"We remembered not to include it" is not a mechanism, so there are two:

1. **Nothing is derived from a model.** Every serializer here is a plain
   ``Serializer`` with an explicit field list, not a ``ModelSerializer``. A
   ``ModelSerializer`` grows a field when a *model* grows a column, which is
   exactly how the answer to a question type invented next year gets published
   by code nobody edited.
2. **A forbidden name cannot be declared.** :class:`_PlaySerializer` checks its
   subclasses' fields at class-creation time, so a serializer emitting
   ``is_correct`` fails at **import** — the app does not start, rather than
   starting and leaking. ``tests.test_serializers`` walks the module for the same
   set, which catches the field this list has not thought of yet.

The other rule here is that **the board is shuffled per matchup, not per
player**. Both sides must see the options in the same order: a match is a race,
and a race where the two players are reading different boards is not one. So the
order is a deterministic function of the matchup and the question
(:func:`shuffle_seed`) rather than of the request — and it is a shuffle at all
because the authored order puts the correct option first often enough that
"always pick the top one" would beat guessing.
"""

from __future__ import annotations

import random

from rest_framework import serializers

from apps.questions.models import QUESTION_MODELS, QuestionType

__all__ = [
    "FORBIDDEN_FIELD_NAMES",
    "QUESTION_SERIALIZERS",
    "FreeTextPlaySerializer",
    "ImageAnswerPlaySerializer",
    "MatrixPlaySerializer",
    "MultipleAnswerPlaySerializer",
    "OrderingPlaySerializer",
    "SingleAnswerPlaySerializer",
    "TrueFalsePlaySerializer",
    "serialize_for_play",
    "shuffle_seed",
]

#: Every field name that identifies a correct answer, by the name it carries on
#: a model. Checked against both a field's name and its ``source``, because
#: ``label = CharField(source="answer")`` is the version of this mistake that a
#: name check alone would miss.
#:
#: Add to this set when a question type adds a column that says what is true —
#: it is cheap here and expensive in a live match.
FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "accepted_answers",
        "answer",
        "answers",
        "cells_answer",
        "correct",
        "correct_position",
        "is_correct",
        "solution",
        "value",
    }
)


class _PlaySerializer(serializers.Serializer):
    """Base for every play-time serializer, and the check that guards them.

    The check runs when a subclass is *created*, which is when this module is
    imported — so a serializer that would publish an answer stops the process
    from booting instead of stopping a match from being fair.
    """

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        for name, field in cls._declared_fields.items():
            source = getattr(field, "source", None) or ""
            offending = {name, *source.split(".")} & FORBIDDEN_FIELD_NAMES
            if offending:
                raise TypeError(
                    f"{cls.__name__} declares {name!r}"
                    f"{f' (source {source!r})' if source else ''}, which names an "
                    f"answer: {', '.join(sorted(offending))}. A play-time payload "
                    f"may not carry it — the player is racing a clock to work it out."
                )

    def shuffled(self, options) -> list:
        """``options`` in this matchup's order — the same order for both players.

        The seed comes from the context rather than from ``random``'s own state,
        so the two consumers serving the two players produce the same board
        without talking to each other. A serializer used outside a matchup (the
        admin, a schema example) has no seed and gets the authored order, which
        is why :func:`serialize_for_play` is the entry point the match engine
        calls: it makes the seed a required argument, so the play path cannot
        reach here without one.
        """
        items = list(options)
        seed = self.context.get("shuffle_seed")
        if seed is None:
            return items
        random.Random(seed).shuffle(items)
        return items


# --- The pieces a question is built out of -----------------------------------


class _TextOptionSerializer(_PlaySerializer):
    """An option the player can pick, and the id they pick it by.

    The id is what a submission names (``schemas.answers.OptionId``), which is
    why it is here and why it has to be: a payload naming options by text would
    make two options with the same wording one option, and would let a client
    answer with text the server never offered.
    """

    id = serializers.IntegerField(read_only=True)
    text = serializers.CharField(read_only=True)


class _ImageOptionSerializer(_PlaySerializer):
    id = serializers.IntegerField(read_only=True)
    image = serializers.SerializerMethodField()
    #: Alt text. It names *which* option this is, not whether it is right, so it
    #: is safe: every option carries one, and "Kobe Bryant" beside a photo of
    #: Kobe Bryant is what a screen reader needs, not a hint.
    label = serializers.CharField(read_only=True)

    def get_image(self, option) -> str:
        return option.image.url


class _AxisSerializer(_PlaySerializer):
    """A matrix heading, down the side or along the top."""

    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)


class _CellSerializer(_PlaySerializer):
    """An intersection the player is asked to fill — and nothing about what
    goes in it.

    This is the one place the sparseness of a grid becomes a client's problem:
    the cells a question authors are a subset of rows x columns (see
    ``models.MatrixCell``), so without this list a client would draw an input in
    every square and a player would waste the clock on squares nobody scores.
    """

    row_id = serializers.IntegerField(read_only=True)
    column_id = serializers.IntegerField(read_only=True)


# --- One serializer per question type ----------------------------------------


class _QuestionPlaySerializer(_PlaySerializer):
    """The fields every question shows, whatever its answer shape.

    ``slug`` is deliberately **absent**, though it is the name the question is
    known by everywhere else in the backend. Slugs are authored by hand and are
    written to be readable — ``kobe-81-point-game`` is a perfectly ordinary slug
    and a complete answer. It is not on
    :data:`FORBIDDEN_FIELD_NAMES` because it is not always an answer; it is left
    out because it is *sometimes* one, and a field that leaks depending on how
    somebody worded it cannot be reviewed.
    """

    id = serializers.UUIDField(read_only=True)
    type = serializers.CharField(source="question_type", read_only=True)
    description = serializers.CharField(read_only=True)
    level = serializers.IntegerField(read_only=True)
    category = serializers.CharField(source="category.slug", read_only=True)
    image = serializers.SerializerMethodField()

    def get_image(self, question) -> str | None:
        """The question's own illustration, or nothing.

        Not to be confused with an image-answer question's options: this is a
        picture of the play being asked about (``BaseQuestion.image``), and most
        questions have none.
        """
        return question.image.url if question.image else None


class SingleAnswerPlaySerializer(_QuestionPlaySerializer):
    options = serializers.SerializerMethodField()

    def get_options(self, question) -> list[dict]:
        return _TextOptionSerializer(
            self.shuffled(question.options.all()), many=True, context=self.context
        ).data


class ImageAnswerPlaySerializer(_QuestionPlaySerializer):
    options = serializers.SerializerMethodField()

    def get_options(self, question) -> list[dict]:
        return _ImageOptionSerializer(
            self.shuffled(question.options.all()), many=True, context=self.context
        ).data


class MultipleAnswerPlaySerializer(_QuestionPlaySerializer):
    """Several options are right — and the payload does not say how many.

    A count would be a real help to a player and a real leak: on a four-option
    question, "two of these are correct" halves the search space. The client
    renders checkboxes and the player decides how many to tick.
    """

    options = serializers.SerializerMethodField()

    def get_options(self, question) -> list[dict]:
        return _TextOptionSerializer(
            self.shuffled(question.options.all()), many=True, context=self.context
        ).data


class TrueFalsePlaySerializer(_QuestionPlaySerializer):
    """No options and no answer — the two buttons are the client's.

    The whole risk of this type is one boolean column called ``answer``, which
    the base class's check makes undeclarable here.
    """


class FreeTextPlaySerializer(_QuestionPlaySerializer):
    """The player types it, so there is nothing to send but the question.

    ``accepted_answers`` is the entire answer key and is forbidden by name.
    """


class OrderingPlaySerializer(_QuestionPlaySerializer):
    """The items to arrange, in an order that is not the answer.

    This is the type where the shuffle is not a nicety: the options are stored in
    their correct order (``OrderingOption.correct_position``, and the resource
    file's list order *is* the answer), so emitting them unshuffled hands over
    the solution while carefully omitting the field that states it.
    """

    instruction = serializers.CharField(read_only=True)
    options = serializers.SerializerMethodField()

    def get_options(self, question) -> list[dict]:
        return _TextOptionSerializer(
            self.shuffled(question.options.all()), many=True, context=self.context
        ).data


class MatrixPlaySerializer(_QuestionPlaySerializer):
    """The grid: its headings, and which intersections to fill.

    Headings keep their authored order rather than being shuffled. They are not
    options to be picked but axes to be read, the sparse pattern of cells is what
    makes the grid legible, and a player reading a shuffled set of years against
    a shuffled set of teams is being asked a harder question than the one that
    was written.
    """

    row_count = serializers.IntegerField(read_only=True)
    column_count = serializers.IntegerField(read_only=True)
    rows = serializers.SerializerMethodField()
    columns = serializers.SerializerMethodField()
    cells = serializers.SerializerMethodField()

    def get_rows(self, question) -> list[dict]:
        return _AxisSerializer(question.rows.all(), many=True).data

    def get_columns(self, question) -> list[dict]:
        return _AxisSerializer(question.columns.all(), many=True).data

    def get_cells(self, question) -> list[dict]:
        return _CellSerializer(question.cells.all(), many=True).data


#: One serializer per question type, keyed the way ``models.QUESTION_MODELS``,
#: ``schemas.answers.ANSWER_SUBMISSIONS`` and
#: ``services.evaluation.ANSWER_EVALUATORS`` are. The fourth sibling registry:
#: a type can be asked, shown, answered and scored, and a test walks all four so
#: none of the four can be the one that was forgotten.
QUESTION_SERIALIZERS: dict[str, type[_QuestionPlaySerializer]] = {
    QuestionType.SINGLE_ANSWER: SingleAnswerPlaySerializer,
    QuestionType.IMAGE_ANSWER: ImageAnswerPlaySerializer,
    QuestionType.MULTIPLE_ANSWER: MultipleAnswerPlaySerializer,
    QuestionType.TRUE_FALSE: TrueFalsePlaySerializer,
    QuestionType.FREE_TEXT: FreeTextPlaySerializer,
    QuestionType.ORDERING: OrderingPlaySerializer,
    QuestionType.MATRIX: MatrixPlaySerializer,
}


def shuffle_seed(*, matchup_id, question_id) -> str:
    """The board order for one question of one matchup.

    Deliberately **not** derived from the player, the request or the clock. Two
    processes serving the two sides of a match compute the same seed from the
    same two ids and lay the board out identically, with no coordination and
    nothing stored; a reconnecting player gets the board they left rather than a
    reshuffled one. And because the matchup id is in it, the same question drawn
    in a later match comes up in a different order, so an option's position is
    not something to memorise.
    """
    return f"{matchup_id}:{question_id}"


def serialize_for_play(*, question, matchup_id) -> dict:
    """One question as its two players see it.

    The seam the match engine calls, and the reason it is a function rather than
    a serializer the caller picks: the caller knows a question and a matchup, not
    a question *type*, and making it choose a serializer would put a mapping from
    type to class in ``apps.matches`` — the exact dependency the ``(type, id)``
    pair exists to avoid.

    ``matchup_id`` is required, so the play path cannot produce an unshuffled
    board by omitting it.
    """
    question_type = question.question_type
    serializer_class = QUESTION_SERIALIZERS.get(question_type)
    if serializer_class is None:  # pragma: no cover - a registry gap the suite catches
        raise LookupError(f"No play-time serializer for question type {question_type!r}.")

    return serializer_class(
        question,
        context={
            "shuffle_seed": shuffle_seed(matchup_id=matchup_id, question_id=question.id)
        },
    ).data


# Checked at import, not with an ``assert`` — asserts vanish under ``python -O``,
# and this is one of the checks that must hold in production above all.
_unserialisable = set(QUESTION_MODELS) - set(QUESTION_SERIALIZERS)
if _unserialisable:  # pragma: no cover - the suite asserts the registries agree
    raise ImportError(
        f"No play-time serializer for question type(s): "
        f"{', '.join(sorted(_unserialisable))}. A match could draw a question it "
        f"cannot show."
    )
