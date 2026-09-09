"""The write side of the questions domain.

``sync`` is the whole of it today: the resource files are how questions come
into being, so there is deliberately no service that creates one from a request
payload. Question *selection* — drawing a matchup's 3/5/7 — lives in
``apps.questions.selectors``, since it reads.
"""

from __future__ import annotations

from apps.questions.services.sync import (
    LoadReport,
    load_resources,
    sync_categories,
    sync_questions,
)

__all__ = ["LoadReport", "load_resources", "sync_categories", "sync_questions"]
