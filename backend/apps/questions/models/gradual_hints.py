"""A question that gets easier while you sit on it.

    "Guess the Game"                    year: ____  round: ____  game: ____

    0s   The final score was 93-89
    5s   Draymond Green hit six threes
    10s  "OH, BLOCKED BY JAMES!"
    15s  The series ended 4-3 to Cleveland
    20s  Kyrie hit one of the clutchest threes in the last minute

Every other question type puts everything it will ever say on the board at
once. This one holds most of it back and pays it out on a timer, hardest clue
first, so answering early is worth more than answering completely — which is
the whole point of it in a race, where the other player is watching the same
hints arrive at the same moment.

Two consequences run through the rest of the app:

**The hints are not on the board.** ``api.serializers`` sends the *count* and
the *interval* and no text at all; the text arrives over the socket, one frame
per hint, when the server's clock says it is due
(``apps.matches.consumers``). A hint is a clue on a timer, and a client handed
all five at question-open would be a client worth patching — so "hint" and
"hints" are in ``FORBIDDEN_FIELD_NAMES``, which makes putting one on a board a
failure to *import*, not a failure to notice.

**The answer is several answers.** A question asks for a handful of labelled
fields — year, round, game number — and each is graded on its own, the way a
matrix grid is graded per cell: somebody who has the year and the round but not
the game number knew most of it, and all-or-nothing would score that as knowing
nothing.
"""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .base import BaseQuestion, QuestionType

#: The most hints one question may carry. Five is a ceiling on the *shape*, not
#: a target: a question wanting a sixth clue is one whose first clue was not
#: hard enough, and every hint past the point where the answer is obvious is
#: clock spent watching text appear.
MAX_HINTS = 5

#: The gap between one hint and the next, when the file does not say.
DEFAULT_HINT_INTERVAL_SECONDS = 5

#: The longest gap a file may ask for. A cap because the interval multiplies:
#: five hints at this spacing already puts the last one a minute into a
#: question, and the clock has to outlast the schedule with time left to type
#: (``apps.questions.constants.HINT_ANSWER_WINDOW_SECONDS``, checked when the
#: file is loaded).
MAX_HINT_INTERVAL_SECONDS = 15

#: The most boxes one question may ask the player to fill.
#:
#: A separate number from :data:`MAX_HINTS` even though they happen to be equal:
#: they bound two unrelated things, and a question growing a sixth clue has
#: nothing to do with one growing a sixth box. The cap is here because the
#: fields are typed under a clock — past a handful, the question stops being
#: about knowing the answer and starts being about typing speed, which is the
#: same judgement ``FreeTextQuestion`` makes about listing short spellings.
MAX_ANSWER_FIELDS = 5


class AnswerFieldKind(models.TextChoices):
    """What sort of thing goes in a box — and therefore how big a box to draw.

    A player typing under a clock should not be handed a field the width of a
    sentence to write ``7`` into: a box's size is the clearest thing on the
    board about what it wants, and one that lies about it costs a second of
    "…is that right?" per field. So the kind is **authored**, per field, and the
    client sizes and keyboards from it (a phone opens a number pad for a
    ``number``, which is the other half of the same second).

    Deliberately *not* inferred from the accepted answers, even though "every
    spelling is digits" would be right nearly every time. Inferring it would make
    the board's shape a consequence of the answer key — add ``'16`` as a
    spelling of a year and the box silently becomes a text box — and it would
    mean the width of a field was computed from its answers, which is one step
    from the width being *about* its answers. Nothing here narrows a guess: the
    kind says what to type, never how much of it.
    """

    TEXT = "text", "Text"
    NUMBER = "number", "Number"


class GradualHintsQuestion(BaseQuestion):
    """The question, and how fast its clues come out.

    ``hint_interval_seconds`` is per question rather than a platform constant
    because it is a property of the *clues*: five one-line stat clues want a
    tighter spacing than three clues each of which is a sentence to read. It is
    authored, defaulted, and bounded — see :data:`MAX_HINT_INTERVAL_SECONDS`.

    The reveal schedule is not stored. It is ``hint.order`` times the interval,
    measured from ``MatchupQuestion.started_at`` — the same server stamp both
    players' countdowns run on — so nothing has to be written down per matchup
    and a player who reconnects mid-question recomputes exactly the schedule
    they left. See ``apps.questions.selectors.reveal_schedule``, which is the
    seam the match engine asks for it through.
    """

    hint_interval_seconds = models.PositiveSmallIntegerField(
        default=DEFAULT_HINT_INTERVAL_SECONDS,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_HINT_INTERVAL_SECONDS)],
        help_text="Seconds between one hint being revealed and the next.",
    )

    class Meta(BaseQuestion.Meta):
        pass

    @property
    def question_type(self) -> str:
        return QuestionType.GRADUAL_HINTS


class GradualHint(models.Model):
    """One clue, and its place in the queue.

    ``order`` is 1-based and contiguous, derived from the list order in the
    resource file the way every other position in this app is — so a file
    cannot have a gap, and cannot accidentally reorder the clues by editing a
    number. **Position 1 is the hardest clue**: the reveal is an easing-off, and
    a file that opens with the giveaway has made the other four decorative.

    The text is never sent with the board. It leaves the server one frame at a
    time, at the moment it comes due — see this module's docstring.
    """

    question = models.ForeignKey(
        GradualHintsQuestion, on_delete=models.CASCADE, related_name="hints"
    )
    order = models.PositiveSmallIntegerField()
    text = models.TextField()

    class Meta:
        ordering = ("order",)
        constraints = [
            models.UniqueConstraint(
                fields=["question", "order"], name="uniq_gradual_hint_order"
            )
        ]

    def __str__(self) -> str:
        return f"{self.order}. {self.text}"


class GradualHintsField(models.Model):
    """One box the player types into, and the word above it.

    A field is the unit of credit (see the module docstring), which is why it is
    a row with an id rather than a key in a dict: a submission names the field
    it is answering **by id**, exactly as a matrix cell names its row and column
    by id, so an answer does not depend on how a label happens to be spelled or
    capitalised on the board.
    """

    question = models.ForeignKey(
        GradualHintsQuestion, on_delete=models.CASCADE, related_name="answer_fields"
    )
    order = models.PositiveSmallIntegerField()
    #: What the box is called — "Year", "Round", "Game number". Short: it is a
    #: column heading on a phone, not a sentence.
    label = models.CharField(max_length=60)
    #: Text or number — see :class:`AnswerFieldKind`. Presentation only: it
    #: changes the box and the keyboard, never the comparison, which stays the
    #: same case- and whitespace-folded match for both (``2016`` and ``2016``
    #: are equal as strings, and a number field that accepted ``2016.0`` would
    #: be a different question from the one the file authored).
    kind = models.CharField(
        max_length=16, choices=AnswerFieldKind.choices, default=AnswerFieldKind.TEXT
    )

    class Meta:
        ordering = ("order",)
        constraints = [
            models.UniqueConstraint(
                fields=["question", "order"], name="uniq_gradual_hints_field_order"
            )
        ]

    def __str__(self) -> str:
        return self.label


class GradualHintsFieldAnswer(models.Model):
    """One spelling that fills one field.

    The sibling of :class:`~apps.questions.models.FreeTextAnswer`, for the same
    reason and with the same rule: a player racing a clock types ``7``, not
    ``Game 7``, so a field carries every honest way to write its answer and the
    comparison folds case and whitespace (``apps.questions.matching``). Stored
    as authored so the resource file stays readable.
    """

    field = models.ForeignKey(
        GradualHintsField, on_delete=models.CASCADE, related_name="accepted_answers"
    )
    value = models.CharField(max_length=255)

    class Meta:
        ordering = ("value",)
        constraints = [
            models.UniqueConstraint(
                fields=["field", "value"], name="uniq_gradual_hints_field_answer"
            )
        ]

    def __str__(self) -> str:
        return self.value
