"""Development settings."""

from .base import *  # noqa: F401,F403
from .base import env_list

DEBUG = True

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0")

# A dev SPA proxies /api to Django and rewrites the Host header, but it cannot
# rewrite the browser's Origin header — so Django's CSRF check compares the real
# page origin against this list.
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)

# The Django admin, at the generated prefix `manage.py runserver` prints on
# startup (base.py keeps it off elsewhere). Even here it is not `/admin/`:
# developing against the same URL shape the deployed tiers use is what keeps the
# generated-prefix path exercised rather than theoretical.
ADMIN_ENABLED = True

# Mail to the console: the forgot-password link is printed in the runserver log
# rather than sent, so the flow is walkable end to end with no relay configured.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# On here, and only here (base.py defaults every tier to off): a solo dev
# running just this process has nobody else to be matched against, so
# matchmaking would otherwise hang forever waiting on a second human. Run
# `manage.py seed_bots` once to populate the roster this pairs against.
FF_ENABLE_BOTS_IF_TIMEOUT = True

# --- Development-only API affordances ----------------------------------------
# base.py ships hardened defaults (JSON-only, admin-only schema) since the
# deployed tiers inherit them. Relaxed only here, patched after the import
# rather than `if DEBUG` in base.py — DEBUG is only set True after
# `from .base import *` runs, so a conditional there would miss it.

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_RENDERER_CLASSES": (
        "apps.core_common.renderers.EnvelopeJSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
    "DEFAULT_METADATA_CLASS": "rest_framework.metadata.SimpleMetadata",
}

# /api/schema/ and /api/docs/ are mounted only when DEBUG (see config/urls.py);
# a browser hitting them carries no Bearer token, so the admin-only default
# would 403 the Swagger UI's own schema fetch.
SPECTACULAR_SETTINGS = {
    **SPECTACULAR_SETTINGS,  # noqa: F405
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}
