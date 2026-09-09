"""Matches — scaffolded, not yet built.

The competitive game: the global matchmaking pool, a ``Matchup`` between
exactly two players, the 3/5/7 questions it drew, and each player's answers with
the server-measured response time. Redis and Channels hold who is online and
what is happening right now; this app's tables hold what happened.

The directory carries the layered layout every app here uses (``api/``,
``services/``, ``selectors/``, ``validators/``, ``schemas/``,
``permissions/``) so the shape is decided once rather than re-argued per app,
and the app is listed in ``LOCAL_APPS`` so a model added here is picked up
without a settings edit. No models yet — the plan's tables land with the
increment that has something to do with them.
"""
