"""The maintainers' rehearsal room.

A question is authored in YAML, loaded by ``sync_questions``, and then the next
time anybody sees it is in a live match against a stranger. This app is the step
in between: it lists the catalog, plays any one question exactly as a matchup
would show it, scores what you typed with the evaluator the match engine uses,
and then says what the answer actually was.

**It is for maintainers, and the gates say so twice.** ``TESTER_ENDPOINT_ENABLED``
decides whether ``config/urls.py`` mounts these routes at all (local: on;
staging: on by environment; production: off), and past that
:class:`~apps.tester.permissions.IsMaintainer` refuses anybody whose account is
not ``is_staff`` — which, in this platform, means an account made with
``manage.py createsuperuser``. Neither gate is a substitute for the other: the
flag is what makes the surface not exist on a tier real players use, and the
permission is what makes a tier where it *does* exist safe.

**Why an app of its own rather than a corner of ``apps.questions``.** What this
does is span two domains: the board, the evaluator and the answer key come from
``apps.questions``, while the clock and the points come from ``apps.matches``.
``apps.questions`` may not import ``apps.matches`` — the catalog carries a
``time_limit_seconds`` and has no opinion about what it is worth
(``backend/CLAUDE.md``) — so a tester living there would either lose half of
what makes it a rehearsal, or invert the one dependency the question domain is
defined by. Here it can import both, because nothing imports it.

**It owns no models and writes nothing.** A rehearsal leaves no ``Matchup``, no
``PlayerAnswer`` and no rating change; answering the same question forty times
while fixing its accepted spellings should not put forty rows anywhere or move
anybody up a ladder. That is also why it is safe to hand a maintainer the answer
key here: there is no game in progress for it to be the answer to.
"""
