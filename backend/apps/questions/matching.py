"""The comparison form of a typed answer.

One definition, in a module of its own, because two things fold a player's
typing before comparing it — ``services.evaluation`` (a free-text answer, a
matrix cell) and ``rosters`` (a name looked up in the baked CSV) — and a grid
whose evaluator folds a name one way while its index folded it another is a
question with right answers nobody can type.
"""

from __future__ import annotations

__all__ = ["normalise_answer"]


def normalise_answer(value: str) -> str:
    """Casefolded and whitespace-collapsed, so ``"  kobe   BRYANT "`` matches
    ``"Kobe Bryant"``.

    Applied to *both* sides, which is what lets the resource files stay readable
    (``accepted_answers`` is authored as people spell it, not as a list of
    lowercase keys) — and why an author cannot accidentally make an answer
    unreachable with a trailing space.

    Casefold rather than lower: it is the one that folds the non-English forms a
    player's keyboard can produce, and a name is exactly the kind of word that
    has them.
    """
    return " ".join(value.split()).casefold()
