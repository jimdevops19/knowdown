"""The name a log line should call a thing by.

Every helper turns a model into readable text rather than an id, because a line
identified by a UUID can only be read with a database beside it. Two rules keep
this module cheap and importable everywhere:

- **It never imports an app.** Everything is duck-typed via ``getattr``, so
  ``shared`` stays underneath every app rather than beside them.
- **It never triggers a query.** A label is built from fields already loaded on
  the object handed in.

Every helper is ``None``-safe, so an optional relation passes straight through.
"""

from __future__ import annotations

from typing import Any


def user(value: Any) -> str | None:
    """The account's email — the only identifier a person recognises here."""
    if value is None:
        return None
    return getattr(value, "email", None) or str(value)


def player(value: Any) -> str | None:
    """The competitor's display name, as printed on every scoreboard."""
    if value is None:
        return None
    return getattr(value, "display_name", None) or str(value)


def category(value: Any) -> str | None:
    """A category's slug — ``nba``, ``premier-league``. Short and stable."""
    if value is None:
        return None
    return getattr(value, "slug", None) or str(value)


def question(value: Any) -> str | None:
    """A question's slug, which is also the key its YAML entry is authored under."""
    if value is None:
        return None
    return getattr(value, "slug", None) or str(value)
