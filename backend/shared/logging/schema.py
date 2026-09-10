"""The whitelist of extra fields a log line may carry.

``JSONLogger`` rejects any keyword not listed here, so one concept keeps one key
across the whole backend instead of each call site inventing its own spelling of
it (``question``/``question_slug``/``q``). Adding a field means adding it here,
with a comment saying what it holds.

**Entities go in as labels, never as ids.** There is deliberately no
``question_id``/``player_id``/``matchup_id``: a line identified by a UUID can
only be read with a database beside it, so nobody reads them.
``shared.logging.labels`` turns a model into the name a person uses for it.
Correlation is ``request_id``'s job — every line of one request shares it.
"""

from __future__ import annotations

SUPPORTED_LOG_FIELDS: frozenset[str] = frozenset(
    {
        # --- HTTP / access log ----------------------------------------------
        "method",          # HTTP verb
        "path",            # request path
        "route",           # the resolved URL name, e.g. "v1:categories:list"
        "status_code",     # HTTP status returned
        "duration_ms",     # how long the request took
        "anonymous",       # True when nobody was signed in
        "caller",          # "user" | "probe" — a person, or the kubelet
        "redirect_to",     # Location, on a 3xx
        # --- Authentication ---------------------------------------------------
        "auth_method",     # "password" | "google" | "password+google" | "none"
        "retry_after",     # seconds a refused caller must wait (see accounts.lockout)
        # --- Errors ----------------------------------------------------------
        "code",            # a DomainError's machine-readable code
        "reason",          # its human-readable message
        # --- Realtime (apps.matches) -------------------------------------------
        "action",          # short verb for what happened, e.g. a dropped event's type
        "state",           # a presence/pool state, e.g. "searching" | "offline"
        "close_code",      # the WebSocket close code a socket was shut with
        # --- Entities, as labels (see labels.py) ------------------------------
        "user",            # the account's email
        "player",          # the player's display name
        "category",        # a category's slug, e.g. "nba"
        "question",        # a question's slug
        "question_type",   # a QuestionType value, e.g. "single-answer"
        # --- Resource sync ----------------------------------------------------
        "summary",         # a LoadReport rendered as "3 created, 1 updated..."
        "file",            # the resource file being read
        "count",           # a plain tally the message names
    }
)


class UnsupportedLogFieldError(ValueError):
    """Raised when a call site passes a field that is not on the schema."""

    def __init__(self, fields: set[str]) -> None:
        names = ", ".join(sorted(fields))
        super().__init__(
            f"Unsupported log field(s): {names}. Add them to "
            "shared.logging.schema.SUPPORTED_LOG_FIELDS if they belong there."
        )
