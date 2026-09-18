"""Building a bot's submission, once its verdict is chosen.

``apps.matches.bots.controller`` decides *whether* a bot answers correctly
(a coin flip weighted by ``BotProfile.accuracy``) before it ever looks at a
question; this module's only job is to turn that yes/no into a payload shaped
the way ``apps.questions.schemas.answers`` and
``apps.questions.services.evaluation`` expect — the same payload a real
client's ``ANSWER_SUBMIT`` frame would carry.

One builder per answer shape, keyed by ``QuestionType`` exactly the way
``ANSWER_EVALUATORS`` is (see ``backend/CLAUDE.md``'s note on the four sibling
registries) — a bot answering a question type is subject to the same "walk
every registry together" coverage as asking and scoring one
(``apps.questions.tests.test_evaluation.RegistryCoverageTests``), which is why
this module has its own such test.

Reads the question's own rows directly (``question.options``,
``question.answer``, ...) rather than the play-time serialized board: a bot
runs entirely server-side and is not the audience the anti-cheat shuffle in
``apps.questions.api.serializers`` exists to defend against — it is not sent
anything to leak. It calls the same ``submit_answer`` a real client's answer
would go through, so the evaluator scores it exactly as strictly.
"""

from __future__ import annotations

import random
import uuid
from typing import Callable

from apps.questions.career_stats import load_career_stats
from apps.questions.models import (
    BaseQuestion,
    ColumnsRowsQuestion,
    GradualHintsQuestion,
    NameAsManyQuestion,
    QuestionType,
)

__all__ = ["build_bot_answer"]


def _one_option(*, question: BaseQuestion, correct: bool) -> dict:
    options = list(question.options.values_list("id", "is_correct"))
    correct_ids = [option_id for option_id, is_correct in options if is_correct]
    wrong_ids = [option_id for option_id, is_correct in options if not is_correct]
    if correct:
        chosen = random.choice(correct_ids)
    else:
        chosen = random.choice(wrong_ids) if wrong_ids else random.choice(correct_ids)
    return {"type": question.question_type, "option_id": chosen}


def _multiple_answer(*, question: BaseQuestion, correct: bool) -> dict:
    """The exact correct set, or a deliberately mismatched one.

    ``_evaluate_multiple`` (``apps.questions.services.evaluation``) scores by
    exact set equality, so "wrong" only needs *one* option out of place: adding
    a wrong option if one exists, else dropping a correct one if more than one
    was authored. If neither move is available (exactly one option, and it is
    correct) there is no well-formed wrong submission at all, and the bot
    answers correctly regardless of its chosen verdict.
    """
    options = list(question.options.values_list("id", "is_correct"))
    correct_ids = {option_id for option_id, is_correct in options if is_correct}
    wrong_ids = [option_id for option_id, is_correct in options if not is_correct]

    chosen = set(correct_ids)
    if not correct:
        if wrong_ids:
            chosen.add(random.choice(wrong_ids))
        elif len(chosen) > 1:
            chosen.discard(next(iter(chosen)))
    return {"type": QuestionType.MULTIPLE_ANSWER, "option_ids": sorted(chosen)}


def _true_false(*, question: BaseQuestion, correct: bool) -> dict:
    answer = question.answer if correct else not question.answer
    return {"type": QuestionType.TRUE_FALSE, "answer": answer}


def _free_text(*, question: BaseQuestion, correct: bool) -> dict:
    if correct:
        text = question.accepted_answers.values_list("value", flat=True).first()
    else:
        text = f"not-the-answer-{uuid.uuid4().hex[:8]}"
    return {"type": QuestionType.FREE_TEXT, "text": text}


def _ordering(*, question: BaseQuestion, correct: bool) -> dict:
    positions = dict(question.options.values_list("id", "correct_position"))
    expected = sorted(positions, key=lambda option_id: positions[option_id])
    if correct or len(expected) < 2:
        chosen = expected
    else:
        chosen = expected.copy()
        chosen[0], chosen[1] = chosen[1], chosen[0]
    return {"type": QuestionType.ORDERING, "option_ids": chosen}


def _matrix(*, question: ColumnsRowsQuestion, correct: bool) -> dict:
    # A cell accepts several answers; a bot needs one of them, so it takes the
    # first — ``MatrixCellAnswer`` orders by ``probability_score``, which makes
    # that the most obvious pick rather than an arbitrary one.
    submitted = []
    for cell in question.cells.prefetch_related("answers"):
        answer = cell.answers.first()
        value = (
            answer.value
            if correct and answer is not None
            else f"wrong-{uuid.uuid4().hex[:6]}"
        )
        submitted.append(
            {"row_id": cell.row_id, "column_id": cell.column_id, "answer": value}
        )
    return {"type": QuestionType.MATRIX, "cells": submitted}


def _gradual_hints(*, question: GradualHintsQuestion, correct: bool) -> dict:
    """Every box filled in — right, or uniformly wrong.

    Fills all of them either way rather than a random subset, because a bot
    leaving boxes blank would be scoring itself a fraction on top of the
    accuracy its ``BotProfile`` already decides (the question is credited per
    field — ``apps.questions.services.evaluation``), and two dice for one
    outcome is a bot whose configured accuracy means nothing.

    A bot does not wait for the clues. It is answering from the question's own
    rows, which is the same shortcut every builder here takes — see this
    module's docstring — and *when* it answers is the controller's decision, not
    something the reveal schedule is allowed to hurry.
    """
    submitted = []
    for field in question.answer_fields.prefetch_related("accepted_answers"):
        accepted = field.accepted_answers.first()
        text = (
            accepted.value
            if correct and accepted is not None
            else f"wrong-{uuid.uuid4().hex[:6]}"
        )
        submitted.append({"field_id": field.id, "text": text})
    return {"type": QuestionType.GRADUAL_HINTS, "answer_fields": submitted}


def _name_as_many(*, question: NameAsManyQuestion, correct: bool) -> dict:
    """Names picked off the top of the qualifying list until the target is met.

    The bot reads the same artifact the evaluator does
    (``apps.questions.career_stats``) rather than a board, which is the
    shortcut every builder here takes — see this module's docstring.

    **It takes the most obvious names, not the best ones.** A bot that reached
    for the deepest cuts would need two names where a person needs six, and
    would be a strictly better player than any human at exactly this type; its
    strength is supposed to come from its ``BotProfile``, not from the shape of
    a registry entry. So it plays the list the way a person does — from the
    top, stopping when it has enough — and the accuracy dice have already
    decided whether it gets there at all.
    """
    if not correct:
        # Names nobody has, so the list is well-formed and worth nothing: the
        # counterpart of the ``not-the-answer-…`` a free-text bot types.
        return {
            "type": QuestionType.NAME_AS_MANY,
            "names": [f"Nobody Atall {uuid.uuid4().hex[:6]}"],
        }

    qualifiers = load_career_stats().qualifiers(
        stat=question.stat,
        comparison=question.comparison,
        threshold=question.threshold,
    )
    names, earned = [], 0
    for player in qualifiers.players:
        if earned >= question.target_score:
            break
        names.append(player.name)
        earned += player.probability_score

    # A question whose board cannot reach its target is refused at load time,
    # so this is only reachable for a row written by hand in the admin. One
    # name keeps the payload well-formed (the schema needs at least one) and
    # lets the evaluator score it honestly short.
    return {
        "type": QuestionType.NAME_AS_MANY,
        "names": names or [f"Nobody Atall {uuid.uuid4().hex[:6]}"],
    }


#: One builder per ``QuestionType`` — the sibling of ``ANSWER_EVALUATORS``
#: (``apps.questions.services.evaluation``) for the write side a bot needs.
BOT_ANSWER_BUILDERS: dict[str, Callable[..., dict]] = {
    QuestionType.SINGLE_ANSWER: _one_option,
    QuestionType.IMAGE_ANSWER: _one_option,
    QuestionType.MULTIPLE_ANSWER: _multiple_answer,
    QuestionType.TRUE_FALSE: _true_false,
    QuestionType.FREE_TEXT: _free_text,
    QuestionType.ORDERING: _ordering,
    QuestionType.MATRIX: _matrix,
    QuestionType.GRADUAL_HINTS: _gradual_hints,
    QuestionType.NAME_AS_MANY: _name_as_many,
}


def build_bot_answer(*, question: BaseQuestion, correct: bool) -> dict:
    """A payload for ``apps.matches.services.submit_answer`` — deliberately
    correct or deliberately wrong, per ``question``'s own answer key.

    Raises ``KeyError`` for a question type with no builder, the same way an
    evaluator gap raises rather than silently scoring zero — a bot must never
    silently sit a question out because a registry line was missed.
    """
    builder = BOT_ANSWER_BUILDERS[question.question_type]
    return builder(question=question, correct=correct)
