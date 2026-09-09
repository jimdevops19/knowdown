"""
Base settings shared across all environments.

Environment-specific overrides live in ``local.py``, ``production.py`` and
``test.py``. Select one with the ``DJANGO_SETTINGS_MODULE`` environment
variable (defaults to ``config.settings.local`` for manage.py / asgi / wsgi).

Configuration is read from the environment (12-factor). A ``.env`` file at the
repository root is loaded in development; see ``.env.example``.
"""

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import dj_database_url
from dotenv import load_dotenv

from shared.admin_url import resolve_admin_url

# backend/config/settings/base.py -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load a repo-root .env if present (a no-op when absent, e.g. in production
# where real environment variables are provided by the platform).
load_dotenv(BASE_DIR.parent / ".env")


# --- Small env helpers -------------------------------------------------------

def env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, str(default)))


def env_list(key: str, default: str = "") -> list[str]:
    raw = os.environ.get(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Core --------------------------------------------------------------------

# Overridden per-environment; kept insecure here only so dev works with no .env.
SECRET_KEY = env("SECRET_KEY", "django-insecure-change-me-in-env")

DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")


# --- Applications ------------------------------------------------------------

DJANGO_APPS = [
    # Must precede django.contrib.staticfiles: `runserver` is otherwise the
    # WSGI one, and websockets would 404 in local development only — the most
    # confusing possible place for them to fail.
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS: list[str] = [
    "channels",
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
]

# Local apps live under apps/ and are imported via the ``apps`` package.
#
# players / matches / rankings / achievements are scaffolds today: the layered
# directory layout and nothing else. They are listed anyway so a model added to
# one is picked up without a settings edit, and so `startapp`'s output has
# somewhere to go.
LOCAL_APPS: list[str] = [
    "apps.core_common",
    "apps.accounts",
    "apps.players",
    "apps.categories",
    "apps.questions",
    "apps.matches",
    "apps.rankings",
    "apps.achievements",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves STATIC_ROOT from gunicorn. The only static this backend has is the
    # admin's own CSS/JS — an SPA's assets are its own server's job — so this
    # exists to make the admin look like the admin, and nothing else.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Attaches a per-request id used in log records and the error envelope.
    "apps.core_common.middleware.RequestIDMiddleware",
    # One structured access-log line per request. Inside RequestIDMiddleware so
    # its lines carry the request id.
    "apps.core_common.middleware.AccessLogMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# --- Database ----------------------------------------------------------------
# Parsed from DATABASE_URL (dj-database-url). Falls back to local sqlite so the
# project runs with no configuration in development.

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600 if env_bool("DB_PERSISTENT", False) else 0,
    )
}


# --- Realtime (Channels channel layer) ---------------------------------------
# This is what will carry the global matchmaking pool and the live state of a
# matchup: who is online, which question is up, and the server-side clock that
# decides who answered first. PostgreSQL stores what happened; Redis holds what
# is happening right now.
#
# With no REDIS_URL, falls back to an in-memory layer. That is not a degraded
# Redis but a *per-process* layer — correct exactly when one process does every
# job, which is true of `runserver` and the test suite and false of every
# container deployment. It is what keeps the project runnable zero-config.

REDIS_URL = env("REDIS_URL", "")

CHANNEL_LAYERS = {
    "default": (
        {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                # Must stay above channels_redis's brpop_timeout (5s). A waiting
                # consumer blocks on `BRPOP <channel> 5`, and redis-py's default
                # read timeout is also 5s — so without this margin the client
                # gives up right as the server answers, killing idle sockets.
                "hosts": [{"address": REDIS_URL, "socket_timeout": 20}],
            },
        }
        if REDIS_URL
        else {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    )
}


# --- Cache -------------------------------------------------------------------
# Must be shared, not per-process: Django's LocMemCache is private to each
# worker, so DRF throttling would count per-worker instead of platform-wide
# ("60/min" becoming 60 per pod). Defaults to the channel layer's Redis on a
# separate DB index (a FLUSHDB on one can't wipe the other).

def _on_redis_db(url: str, db: int) -> str:
    """Same Redis server, different logical database."""
    return urlunsplit(urlsplit(url)._replace(path=f"/{db}"))


REDIS_CACHE_URL = env("REDIS_CACHE_URL", "") or (
    _on_redis_db(REDIS_URL, 1) if REDIS_URL else ""
)

CACHES = {
    "default": (
        {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_CACHE_URL,
            "KEY_PREFIX": "knowdown",
            "OPTIONS": {
                # A dead cache must not break the request: reads miss, writes
                # drop. Throttling therefore fails *open* — worth knowing.
                "socket_connect_timeout": 2,
                "socket_timeout": 2,
            },
        }
        if REDIS_CACHE_URL
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "knowdown",
        }
    )
}


# --- Password validation -----------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Internationalization ----------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --- Static & media ----------------------------------------------------------

STATIC_URL = env("STATIC_URL", "static/")
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
# Overridable so a deployment can point this at a writable volume: the runtime
# image ships the code dir read-only by design, so the default below is only
# correct for local dev, where BASE_DIR is the repo checkout.
#
# `sync_questions` copies question images here out of
# apps/questions/resources/<category>/images/ — see apps.questions.services.sync.
MEDIA_ROOT = Path(env("MEDIA_ROOT")) if env("MEDIA_ROOT") else BASE_DIR / "media"


# --- Defaults ----------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user: email is the login identifier (no username). See apps.accounts.
AUTH_USER_MODEL = "accounts.User"


# --- Django REST Framework ---------------------------------------------------

REST_FRAMEWORK = {
    # Bearer token only, on purpose. An SPA served same-origin in dev sends any
    # leftover Django-admin `sessionid` cookie on every API call; with
    # SessionAuthentication enabled DRF would authenticate off that cookie and
    # then demand a CSRF token, breaking anonymous POSTs. Cookies carry no
    # authority over /api/.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core_common.pagination.DefaultPagination",
    "PAGE_SIZE": env_int("PAGE_SIZE", 25),
    # JSON only outside dev. The browsable renderer answers any request with
    # `Accept: text/html`, no extra permission needed — and that HTML page leaks
    # the view docstring, allowed methods, and dropdowns that run their own
    # queries. `local.py` adds it back for dev (it can't be `if DEBUG` here —
    # DEBUG is only set True after `from .base import *` runs).
    "DEFAULT_RENDERER_CLASSES": (
        "apps.core_common.renderers.EnvelopeJSONRenderer",
    ),
    # No OPTIONS metadata outside dev. DRF's default `SimpleMetadata` answers
    # any OPTIONS with the view docstring plus every serializer field with its
    # type, `required`, `max_length` and `choices` — the same API map
    # `/api/schema/` was pulled for. `None` makes OPTIONS a 405; CORS preflight
    # is unaffected (CorsMiddleware answers it before routing).
    "DEFAULT_METADATA_CLASS": None,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ),
    # Consistent JSON envelope + domain-exception translation live in core_common.
    "EXCEPTION_HANDLER": "apps.core_common.exceptions.drf_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # DEFAULT_THROTTLE_RATES below does nothing without these classes named —
    # DRF only reads the rates when a throttle class asks for its scope. Only as
    # real as the cache backing it (see CACHES): needs Redis, or the count is
    # per-worker instead of platform-wide.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", "60/min"),
        "user": env("THROTTLE_USER", "1000/min"),
    },
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ("v1",),
}


# --- SimpleJWT ---------------------------------------------------------------
# Configured now so the shape is settled; no auth endpoints are mounted yet
# (apps/accounts is the User model and nothing else this increment).

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("ACCESS_TOKEN_MINUTES", 30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("REFRESH_TOKEN_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}


# --- drf-spectacular (OpenAPI schema) ----------------------------------------

SPECTACULAR_SETTINGS = {
    "TITLE": "Knowdown API",
    "DESCRIPTION": "Real-time 1v1 trivia — REST API.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    "COMPONENT_SPLIT_REQUEST": True,
    # Backup for config/urls.py: the schema routes are only mounted when DEBUG,
    # but drf-spectacular defaults to AllowAny — so pin the permission here too,
    # in case these views are ever mounted elsewhere.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
    "SERVE_AUTHENTICATION": [
        "rest_framework_simplejwt.authentication.JWTAuthentication"
    ],
}


# --- CORS --------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
)
CORS_ALLOW_CREDENTIALS = True


# --- Client IP on log lines --------------------------------------------------
# How many reverse proxies in front of Django are trusted to have appended an
# honest hop to X-Forwarded-For. 0 (the default) means don't trust the header at
# all and use the raw socket peer: behind a cluster ingress every request tends
# to arrive NAT'd through the same few internal hops, so trusting it blind logs
# every visitor as the gateway. Raise it only where the forwarding chain in
# front of a given deployment has been confirmed.
TRUSTED_PROXY_HOPS = env_int("TRUSTED_PROXY_HOPS", 0)


# --- Django admin ------------------------------------------------------------
# Off by default, and never at `/admin/`. The admin is ~120 URLs of direct
# database access sitting outside DRF, so no throttle covers its login form.
# `local.py` turns it on; the prefix comes from ADMIN_URL, and with none set a
# random 40-character one is generated per process — `manage.py runserver`
# prints what it chose, which is the only place it is ever announced.

ADMIN_ENABLED = env_bool("ADMIN_ENABLED", False)
ADMIN_URL = resolve_admin_url()


# --- Logging -----------------------------------------------------------------
# Structured JSON logging (shared.logging.JSONFormatter); the request id is
# injected by RequestIDMiddleware via shared.logging.RequestIDFilter.

LOG_TO_FILE = env_bool("LOG_TO_FILE", False)
LOG_FILE_PATH = Path(env("LOG_FILE_PATH", str(BASE_DIR / "logs" / "app.log")))

_active_handlers = ["console", "file"] if LOG_TO_FILE else ["console"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "shared.logging.RequestIDFilter"},
    },
    "formatters": {
        "json": {"()": "shared.logging.JSONFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "json",
        },
        **(
            {
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filters": ["request_id"],
                    "formatter": "json",
                    "filename": str(LOG_FILE_PATH),
                    "maxBytes": 10 * 1024 * 1024,
                    "backupCount": 5,
                }
            }
            if LOG_TO_FILE
            else {}
        ),
    },
    "root": {"handlers": _active_handlers, "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {
            "handlers": _active_handlers,
            "level": "WARNING",
            "propagate": False,
        },
    },
}

if LOG_TO_FILE:
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
