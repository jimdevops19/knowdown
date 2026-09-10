"""Production settings.

Everything here is a tightening of base.py, and every one of them assumes TLS
terminates in front of Django.
"""

from .base import *  # noqa: F401,F403
from .base import env, env_bool

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
