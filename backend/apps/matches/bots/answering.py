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

from apps.questions.models import BaseQuestion, ColumnsRowsQuestion, QuestionType

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
    cells = list(question.cells.values_list("row_id", "column_id", "answer"))
    submitted = []
    for row_id, column_id, answer in cells:
        value = answer if correct else f"wrong-{uuid.uuid4().hex[:6]}"
        submitted.append({"row_id": row_id, "column_id": column_id, "answer": value})
    return {"type": QuestionType.MATRIX, "cells": submitted}


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
