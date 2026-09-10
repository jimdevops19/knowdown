"""CPU opponents — the matchmaking pool's fallback when no human shows up.

Gated end to end by ``settings.FF_ENABLE_BOTS_IF_TIMEOUT``; with it off none of
this package is ever reached (``apps.matches.consumers.MatchmakingConsumer``
is the one caller). See ``Knowdown-ARCH.md`` at the repo root for the full
design — this docstring is the short version:

- ``selection`` — which bot ``Player`` to hand a lonely human, drawn from the
  roster ``manage.py seed_bots`` writes.
- ``answering`` — building a submission for a bot's chosen verdict
  (correct/incorrect) per question type, the same registry shape
  ``apps.questions.services.evaluation.ANSWER_EVALUATORS`` uses.
- ``controller`` — the loop that drives a bot's side of one live matchup
  through ``apps.matches.services``, exactly the calls a real
  ``MatchupConsumer`` would make on a human's behalf, minus the socket.

A bot is an ordinary ``Player`` row (``is_bot=True``) with one
``apps.matches.models.BotProfile`` beside it. Nothing in ``apps.questions``,
``apps.rankings`` or ``apps.achievements`` knows the difference — a bot's
rating moves, its badges are earned, and its games show up in match history
exactly like anyone else's.
"""

from __future__ import annotations
