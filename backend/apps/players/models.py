"""Players — scaffolded, not yet built.

A ``Player`` is the competitor: a display name, an avatar and a
one-to-one back to ``accounts.User``. Game statistics stay out of it — a rating
belongs to ``apps.rankings``, which is scoped per category, and a match record
belongs to ``apps.matches``.

The directory carries the layered layout every app here uses (``api/``,
``services/``, ``selectors/``, ``validators/``, ``schemas/``,
``permissions/``) so the shape is decided once rather than re-argued per app,
and the app is listed in ``LOCAL_APPS`` so a model added here is picked up
without a settings edit. No models yet — the plan's tables land with the
increment that has something to do with them.
"""
