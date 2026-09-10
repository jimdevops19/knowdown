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
    # allauth scopes a social app to a Site; nothing else here uses one.
    "django.contrib.sites",
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
    # Revoked refresh tokens. Without this app `logout/` is a cookie deletion
    # and nothing more: the token itself stays valid until it expires, up to a
    # week later, so a copy taken beforehand would still work.
    "rest_framework_simplejwt.token_blacklist",
    # Sign-in with Google. allauth is the provider machinery; dj_rest_auth is
    # the JSON layer over it (and the HttpOnly refresh cookie). Both are here
    # unconditionally even where no Google app is configured — an unconfigured
    # provider is a *missing app registration*, not a missing dependency, and
    # `/api/v1/auth/config/` is what says which it is.
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "dj_rest_auth",
    "dj_rest_auth.registration",
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
    "apps.ops",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # The admin's door (ADMIN_GATE_ENABLED only; removes itself otherwise via
    # MiddlewareNotUsed). Above WhiteNoise so it can refuse an admin asset
    # before WhiteNoise serves it, and above everything that reads
    # request.path so the path rewrite it does has already happened by the
    # time anything looks.
    "apps.ops.middleware.AdminGateMiddleware",
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
    # Required by allauth >= 65. It only touches the social login flow; the
    # Bearer-token API never sees it do anything.
    "allauth.account.middleware.AccountMiddleware",
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
# `config/settings/production.py` overrides the default to the `/data` volume
# `backend/Dockerfile` creates, so a deployment need not set this itself.
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
        # Password sign-in and signup (LoginView, RegisterView, GoogleLoginView).
        # The `anon` ceiling above is sized for browsing, not for guarding a
        # password — at 60/min one client can work through a word list all day.
        # Scoped separately so tightening sign-in never touches anonymous reads.
        "login": env("THROTTLE_LOGIN", "10/min"),
        # Forgot-password. Separate from `login` because the request half sends
        # real mail on every hit whether or not the address exists, so sharing
        # login's ceiling would let one client walk a mailing list.
        "password_reset": env("THROTTLE_PASSWORD_RESET", "5/min"),
    },
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ("v1",),
}


# --- SimpleJWT ---------------------------------------------------------------
# The access token is short-lived and lives in the client's memory; the
# refresh token never reaches JavaScript at all (see REST_AUTH below).

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("ACCESS_TOKEN_MINUTES", 30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("REFRESH_TOKEN_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": True,
    # A rotated token is a spent token. Without this, the refresh token a
    # client posted stays valid alongside the one it was traded for, so a
    # stolen copy keeps working for the rest of its week.
    "BLACKLIST_AFTER_ROTATION": True,
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


# --- Authentication / allauth ------------------------------------------------

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# allauth on an email-only user model: no username field exists to key on.
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# No confirmation flow is wired for a client yet, and "optional" still sends a
# verification mail whose link is built from a URL name these namespaced routes
# do not expose — which 500s the signup that triggered it.
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"

# The refresh token rides an HttpOnly cookie rather than the response body, so
# it is invisible to JavaScript: the access token — short-lived, kept in memory
# by the client — is the only credential a script on the page can ever read. A
# refresh token in localStorage would be a week-long, self-renewing credential
# one XSS away from a permanent account takeover.
#
# The cookie is scoped to the two routes that ever read it (refresh, logout)
# rather than sent on every API call, which costs nothing here because
# JWTAuthentication reads only the Authorization header.
REST_AUTH = {
    "USE_JWT": True,
    "JWT_AUTH_HTTPONLY": True,
    "JWT_AUTH_COOKIE": None,
    "JWT_AUTH_REFRESH_COOKIE": "knowdown_refresh",
    "JWT_AUTH_REFRESH_COOKIE_PATH": "/api/v1/auth/",
    # True in production.py; plain HTTP is what local development serves.
    "JWT_AUTH_SECURE": False,
    # JWT only: no DRF auth-token model.
    "TOKEN_MODEL": None,
    "SESSION_LOGIN": False,
    "USER_DETAILS_SERIALIZER": "apps.accounts.api.serializers.UserSerializer",
}

# Whether this deployment offers an email/password door at all. Off, it
# unmounts token/, registration/ and both password-reset routes
# (apps/accounts/api/urls.py) and a client hides its email forms via
# GET /api/v1/auth/config/. On by default: password is the door this product
# ships with, and Google is the addition.
PERMIT_PASSWORD_AUTH = env_bool("PERMIT_PASSWORD_AUTH", True)


# --- Sign-in lockout ---------------------------------------------------------
# What happens when one address is guessed at repeatedly. The `login` throttle
# scope above caps the rate per client; these cap the *number* of wrong answers
# one address may give, which is the dimension that survives an attacker
# changing IP. The mechanism is apps/accounts/services/lockout.py.

# Counting only, when off: failures are still tallied and logged, nobody is
# turned away. That is how the numbers become real before the limit starts
# refusing people — and it is what the test settings switch off, so the suite's
# deliberate wrong passwords do not lock an address for a later test.
LOGIN_LOCKOUT_ENFORCED = env_bool("LOGIN_LOCKOUT_ENFORCED", True)

# How long failures are remembered, and so the width of the whole budget:
# LOGIN_LOCKOUT_AFTER guesses per window, not per day.
LOGIN_FAILURE_WINDOW_SECONDS = env_int("LOGIN_FAILURE_WINDOW_SECONDS", 15 * 60)

# Free failures before the cooldowns start. Three is "I tried my two usual
# passwords and a typo" — punishing the honest case turns this into a support
# queue.
LOGIN_DELAY_AFTER = env_int("LOGIN_DELAY_AFTER", 3)

# The cooldown doubles per failure past that (1s, 2s, 4s ...) up to this. Costs
# a person who is nearly right a few seconds; costs a script the difference
# between a word list and about a hundred guesses an hour.
LOGIN_DELAY_CAP_SECONDS = env_int("LOGIN_DELAY_CAP_SECONDS", 60)

# Failures at which the cooldowns become a lock.
LOGIN_LOCKOUT_AFTER = env_int("LOGIN_LOCKOUT_AFTER", 10)

# How long that lock holds. Temporary by design: a lock that had to be lifted
# by hand would be a way to keep a rival out of their own account, so this is
# the wait, not a ban.
LOGIN_LOCKOUT_SECONDS = env_int("LOGIN_LOCKOUT_SECONDS", 15 * 60)

# Count the client IP as a second dimension. OFF by default and dangerous to
# turn on blind: behind an ingress that does not forward the real address every
# request arrives as the same one, so an IP lock there locks out everybody at
# once. Same caution as TRUSTED_PROXY_HOPS above.
LOGIN_LOCKOUT_BY_IP = env_bool("LOGIN_LOCKOUT_BY_IP", False)


# --- Match abuse limits -------------------------------------------------------
# The WebSocket half of the same idea: answering and joining the matchmaking
# pool are the two actions a live match costs the platform for, and a
# concurrent socket is a budget rather than a rate. Mechanism is
# apps.matches.abuse — see its module docstring. Counting only, when off:
# every hit is still tallied and logged, nobody is turned away, which is how
# the numbers become real before the limit starts refusing anyone. The test
# settings switch this off so a suite that opens many sockets in a tight loop
# does not trip its own limit.
MATCH_ABUSE_LIMITS_ENFORCED = env_bool("MATCH_ABUSE_LIMITS_ENFORCED", True)

# Answer frames one player may send per window, across every matchup they are
# in. Sized well above "one per question" (a client answers each question
# once) so a slow connection retrying a frame is never mistaken for abuse.
ANSWER_SUBMIT_RATE_LIMIT = env_int("ANSWER_SUBMIT_RATE_LIMIT", 20)
ANSWER_SUBMIT_RATE_WINDOW_SECONDS = env_int("ANSWER_SUBMIT_RATE_WINDOW_SECONDS", 60)

# Matchmaking-pool joins one player may make per window. Joining costs nothing
# a real match would (no question is drawn until two players are paired),
# which is what makes it the cheapest way to hammer apps.matches.pool's
# pairing mutex.
MATCHMAKING_JOIN_RATE_LIMIT = env_int("MATCHMAKING_JOIN_RATE_LIMIT", 10)
MATCHMAKING_JOIN_RATE_WINDOW_SECONDS = env_int("MATCHMAKING_JOIN_RATE_WINDOW_SECONDS", 60)

# Sockets one player may hold open at once, matchmaking and matchup combined.
# A budget, not a rate: an idle open socket still costs the channel layer and
# apps.matches.presence one slot each, whether or not it ever sends a frame.
MAX_CONCURRENT_SOCKETS_PER_PLAYER = env_int("MAX_CONCURRENT_SOCKETS_PER_PLAYER", 4)

# Safety net for the concurrent-socket counter: how long a slot survives with
# no refresh before it is freed on its own. Longer than any single connection
# should plausibly live without apps.matches.abuse.register_socket refreshing
# it, so it only ever fires for a process that died between registering a
# socket and the disconnect that would have released it.
CONCURRENT_SOCKET_TTL_SECONDS = env_int("CONCURRENT_SOCKET_TTL_SECONDS", 6 * 60 * 60)


# --- CPU (bot) opponents ------------------------------------------------------
# Matchmaking normally waits for a second human. This flag lets it give up on
# that and pair the waiting player against one of the 50 seeded CPU players
# instead (`manage.py seed_bots`, `apps.matches.bots`) rather than leaving them
# in the pool indefinitely. Off by default everywhere — a bot opponent affects
# ratings and match history exactly like a human one, so it is not something a
# production or test run should get for free; `local.py` turns it on so the
# solo-dev loop of "open the app, get a game" works with nobody else online.
FF_ENABLE_BOTS_IF_TIMEOUT = env_bool("FF_ENABLE_BOTS_IF_TIMEOUT", False)

# How long a player waits in a category's pool before the fallback above may
# claim them for a bot match, in seconds. Read by
# `apps.matches.consumers.MatchmakingConsumer`, not by the pool itself — the
# pool only ever holds one waiting slot and does not know why a caller wants it
# freed.
MATCHMAKING_BOT_TIMEOUT_SECONDS = env_int("MATCHMAKING_BOT_TIMEOUT_SECONDS", 8)


# --- Outbound mail -----------------------------------------------------------
# Today there is exactly one message: the forgot-password link
# (accounts.services.password_reset). Django's stock SMTP backend aimed at
# whatever relay the environment names, rather than a provider's API, so
# switching one is an env var and not a new dependency. local.py and test.py
# override the backend itself (console / locmem), and an unset EMAIL_HOST
# anywhere else fails loudly at send time rather than pretending to deliver.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
# 587 (STARTTLS) and 465 (implicit SSL) are mutually exclusive, and smtplib
# refuses a backend with both set — so asking for SSL turns TLS's default off.
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", not EMAIL_USE_SSL)
# smtplib has NO connect/read timeout by default, and the reset mail is sent
# inline on the request thread (there is no queue yet), so an unset timeout
# means a silent relay holds a worker until something upstream kills it.
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "no-reply@knowdown.app")

# Where a reset link points — the client's own origin, never derived from the
# request. Which Host reached this API is a routing detail; it is not a fact
# about which UI can complete a token.
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173")


# --- Google sign-in ----------------------------------------------------------
# Opt-in. Without credentials the provider is left *unconfigured* rather than
# registered with empty strings — an app with a blank client id fails deep
# inside allauth with an opaque error, while an unregistered one lets
# GoogleLoginView say plainly that this server does not offer it.
# GOOGLE_OAUTH_ENABLED is what /api/v1/auth/config/ reports.
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = env("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_ENABLED = bool(GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET)

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    }
}

if GOOGLE_OAUTH_ENABLED:
    SOCIALACCOUNT_PROVIDERS["google"]["APP"] = {
        "client_id": GOOGLE_OAUTH_CLIENT_ID,
        "secret": GOOGLE_OAUTH_CLIENT_SECRET,
        "key": "",
    }

# A social signup mirrors the email one: no verification mail, and the person
# gets their Player row immediately (apps.accounts.adapters).
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_AUTO_SIGNUP = True


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

# With the gate on, ADMIN_URL stops being the secret and becomes an internal
# implementation detail: the mounted prefix 404s from outside no matter what
# it is, and the admin answers only under a token minted by
# `manage.py open_admin` at `/_ops/<token>/<ADMIN_URL>` (apps.ops). Off by
# default — `local.py` runs a plain dev admin at its mounted prefix, since a
# solo developer has no one else who could open it. `production.py` turns it
# on.
ADMIN_GATE_ENABLED = env_bool("ADMIN_GATE_ENABLED", False)


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
