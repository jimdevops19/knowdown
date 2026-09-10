"""Production settings.

Everything here is a tightening of base.py, and every one of them assumes TLS
terminates in front of Django.
"""

from pathlib import Path

from .base import *  # noqa: F401,F403
from .base import env, env_bool
from shared.admin_url import OPS_STATIC_PATH

DEBUG = False

# No fallback: a production process that reaches this with no SECRET_KEY in the
# environment should fail at import, not run on the insecure dev default.
SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY or SECRET_KEY.startswith("django-insecure"):
    raise RuntimeError("SECRET_KEY must be set to a real secret in production.")

if not ALLOWED_HOSTS:  # noqa: F405
    raise RuntimeError("ALLOWED_HOSTS must be set in production.")

# Behind an ingress that terminates TLS: trust its scheme header, then make
# Django refuse plain HTTP itself.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)

# Liveness/readiness probes hit the pod directly over plain HTTP, bypassing
# the ingress that would otherwise set X-Forwarded-Proto — without this,
# SECURE_SSL_REDIRECT 301s every single probe hit, forever, filling the logs
# and, for a *liveness* probe that follows no redirect, reading as the
# process being dead. The probes carry no sensitive data, so exempting them
# from the redirect is safe.
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/"]

SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# The refresh cookie too — it is the longest-lived credential the platform
# hands out, so it must never travel in the clear.
REST_AUTH = {**REST_AUTH, "JWT_AUTH_SECURE": True}  # noqa: F405
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS  # noqa: F405

# The admin is off unless a tier asks for it (ADMIN_ENABLED, still False by
# default here); where it *is* on, it is behind the window gate:
# ADMIN_ENABLED=1 plus ADMIN_GATE_ENABLED=1 plus a fixed ADMIN_URL, which the
# gate then 404s from outside and only opens under a token minted by
# `manage.py open_admin`. STATIC_URL moves under the same `/_ops/` prefix so
# one ingress rule can cover the admin page and the assets it pulls in — see
# OPS_STATIC_PATH in shared.admin_url and apps.ops.middleware.
ADMIN_GATE_ENABLED = env_bool("ADMIN_GATE_ENABLED", True)
STATIC_URL = env("STATIC_URL", OPS_STATIC_PATH)

# base.py's default (BASE_DIR / "media") is only correct for local dev, where
# BASE_DIR is a writable checkout — here it is the image's code dir, which
# `backend/Dockerfile` ships owned by the runtime user but is not where
# anything durable belongs (a rebuilt image starts from the checked-in tree,
# not from what a previous container wrote into it). /data is the volume the
# image already creates for exactly this — the same one a SQLite DATABASE_URL
# would live on — so `sync_questions` writes question images somewhere that
# survives a redeploy with no operator having to point MEDIA_ROOT anywhere
# themselves. Still overridable (object storage mounted as a filesystem, a
# different volume path) via the same MEDIA_ROOT env var base.py reads.
MEDIA_ROOT = Path(env("MEDIA_ROOT", "/data/media"))
