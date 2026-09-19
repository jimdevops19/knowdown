"""The realtime event protocol — every message shape that crosses a socket.

One module, versioned with the API (``ws/v1/``, see ``routing.py``) so a client
author has one place to read the whole contract, the way ``apps.questions``
keeps every answer shape in ``schemas/answers.py``.

Unlike ``apps.core_common``'s REST envelope, these are **not thin pointers a
client refetches** — there is nothing to refetch mid-question, since the point
of the socket is the server's own clock. Every payload here is therefore
**exactly what its name says and nothing else**: the rule that matters most is
the one in ``QUESTION_STARTED`` and ``PLAYER_ANSWERED`` — neither may carry
anything that identifies the correct answer. Only ``QUESTION_RESULT``, sent
once every player has answered or the clock has run out, may.

Channels turns a channel-layer message's ``type`` into the consumer method it
calls, mapping periods to underscores (``match.found`` → ``match_found``) — see
``apps.matches.publish`` and ``apps.matches.consumers``. The client-facing
``type`` strings below use dots for the same reason; they do not have to,
individually, but a socket carrying two conventions is harder to read than one.
"""

from __future__ import annotations

# --- Matchmaking: server → client, over the matchmaking socket --------------

#: Sent once, right after ``connect``, before a pairing is even possible — the
#: client's cue to stop showing a spinner it drew itself and start trusting the
#: server's.
SEARCHING = "searching"

#: A pairing happened. Carries the matchup id and nothing about either
#: player's history — the client switches to the matchup socket
#: (``ws/v1/matches/{matchup_id}/``) to learn anything else.
MATCH_FOUND = "match.found"

# --- Matchup play: server → client, over the matchup socket -----------------

#: One question opened; ``T0`` is the server's, not a promise the client makes
#: itself. Carries the play-time board (``questions.api.serializers.
#: serialize_for_play``) — never a field named ``answer``, ``is_correct``,
#: ``correct_position`` or any of ``FORBIDDEN_FIELD_NAMES``.
#: ``is_tiebreaker`` marks the sudden-death questions a level match is
#: extended by once its agreed board runs out (``services.tiebreak``) — a
#: label for the client, nothing more: such a question is dealt, clocked,
#: answered and closed exactly like any other.
QUESTION_STARTED = "question.started"

#: One clue of a ``gradual-hints`` question came due. Carries the hint's text
#: and its 1-based index, and is the **only** way that text ever reaches a
#: client: the board it arrives beside says how many hints are coming and how
#: far apart, and nothing about what any of them says (``apps.questions.api
#: .serializers.GradualHintsPlaySerializer``). Waiting is what buys a clue, so
#: a client that had been handed all five up front would be playing a different
#: game from the one the question was written as.
#:
#: Unlike every other message here it is sent **per socket, not to the group**.
#: The schedule is a pure function of the question and the server's own
#: ``MatchupQuestion.started_at`` (``apps.questions.selectors.reveal_schedule``),
#: so each connected socket computes the same instants from the same two facts
#: and needs no broadcast to stay in step — and a player who reconnects
#: mid-question is caught up on the clues already due by the same code path,
#: rather than by a replay mechanism of its own. See
#: ``consumers.MatchupConsumer._reveal_hints``.
HINT_REVEALED = "hint.revealed"

#: One player answered. Carries *who*, not *what they said or whether they
#: were right* — the opponent's own clock is still running, and telling them
#: someone else already locked in the correct choice would be exactly the leak
#: ``QUESTION_RESULT`` exists to hold back until both sides are done.
PLAYER_ANSWERED = "player.answered"

#: The question closed — every player answered, or the clock ran out. The one
#: message allowed to carry the answer: per-player correctness, score and
#: response time, plus the concrete answer key itself.
QUESTION_RESULT = "question.result"

#: The matchup reached ``COMPLETED``. Carries the final score line and the
#: winner (or ``None`` on the score/time double-tie ``services.complete_matchup``
#: leaves unbroken) — not ``outcome``. ``outcome`` (``played``/``abandoned``)
#: is a REST/history concern; the socket that watched abandonment happen
#: already knows which one this was.
MATCH_COMPLETED = "match.completed"

#: The opponent disconnected mid-match. Informational only — it starts no
#: clock the client can rely on; ``services.abandon_matchup`` is what actually
#: ends the matchup, after ``RECONNECT_GRACE_SECONDS``, and that ending arrives
#: as an ordinary ``MATCH_COMPLETED``.
OPPONENT_DISCONNECTED = "opponent.disconnected"

#: The opponent's socket came back before the grace period ran out.
OPPONENT_RECONNECTED = "opponent.reconnected"

# --- Both sockets -------------------------------------------------------------

#: A submission the server refused — a malformed payload, a question already
#: closed, a matchup already over. Carries the same ``code``/``message`` shape
#: as a REST 4xx (``core_common.exceptions.DomainError``), so one error model
#: serves both transports.
ERROR = "error"

#: Client → server and back, to hold an idle socket open through a proxy.
PING = "ping"
PONG = "pong"

# --- Client → server, over the matchup socket --------------------------------

#: The only write a client may make over a socket: an answer to the question
#: currently open. Everything else — who the players are, what the question
#: is, whether it is correct — is decided from server state, never trusted off
#: the wire. There is no ``response_time_ms`` field because there is nowhere to
#: put one: ``apps.matches.services.submit_answer`` does not accept it.
ANSWER_SUBMIT = "answer.submit"

#: The only write a client may make over the matchmaking socket, besides
#: connecting: give up the search.
SEARCH_CANCEL = "search.cancel"

#: A player gives up the match on purpose — the deliberate counterpart to
#: ``services.abandon_matchup`` firing off a disconnect timer. Carries no
#: payload: the socket already knows which matchup and which side. Routed
#: through the same ``_abandon`` helper a dropped connection uses, so a
#: forfeit and a timed-out disconnect settle the match identically — the
#: opponent is awarded the win and ``MATCH_COMPLETED`` follows.
FORFEIT = "match.forfeit"
