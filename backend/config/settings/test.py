"""Test settings — optimized for speed."""

from .base import *  # noqa: F401,F403

DEBUG = False

# In-memory database: fast and disposable.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Cheap password hashing to keep fixtures fast.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Never let the test suite reach a real Redis. base.py already picks the
# in-memory layer when REDIS_URL is unset, but a developer with one exported in
# their shell would otherwise have their tests publish into a live channel layer
# — and, worse, pass because of it.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Same reasoning for the cache, with an extra one: a shared Redis cache carries
# state between runs, so a test that passes only because a previous run warmed a
# key is a test that fails on a clean machine.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "knowdown-test",
    }
}

# Throttling is on platform-wide, but the suite must not hit it. Counters live
# in the LocMem cache above and are not cleared between tests, so at the real
# 60/min rate the 61st anonymous request starts 429ing, failing an unrelated
# test depending on run order. Rates are raised here rather than removing the
# throttle classes, so a typo in a scope name still fails. A test that wants
# real throttling asks for it with @override_settings.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10000/min",
        "user": "10000/min",
        # Listed rather than dropped: ScopedRateThrottle raises on a scope with
        # no rate, so leaving one out would fail every sign-in test for the
        # wrong reason. A test that wants the real limit asks for it back.
        "login": "10000/min",
        "password_reset": "10000/min",
    },
}

# Mail goes nowhere and is readable from the test that caused it.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# The password door is what most of the suite signs in through; a tier that
# turns it off unmounts those routes, and testing against an unmounted route is
# testing the URLconf rather than the view.
PERMIT_PASSWORD_AUTH = True

# Sign-in lockout: counted, never enforced. The counters live in the LocMem
# cache above and are not cleared between tests, so the addresses the suite
# signs in wrong with on purpose would accumulate across a run and start 429ing
# an unrelated test depending on order. Switched off rather than removed, so the
# counting and logging path still runs everywhere; the lockout tests ask for the
# real behaviour back with @override_settings(LOGIN_LOCKOUT_ENFORCED=True) and
# clear the cache themselves, the way the throttle tests do above.
LOGIN_LOCKOUT_ENFORCED = False

# The suite is quiet unless something is actually wrong. Every service here logs
# a JSON line per call, and 45 tests' worth of them buries the one line that
# matters — the failure. CRITICAL rather than removing the handler, so the
# formatter and the field schema still run on every line the suite produces: a
# call site passing a field that is not on `shared.logging.schema` still fails
# the test that made the call, which is where that mistake should surface.
LOGGING = {
    **LOGGING,  # noqa: F405
    "root": {**LOGGING["root"], "level": "CRITICAL"},  # noqa: F405
    # `django.request` sets its own level and does not propagate, so the root
    # above cannot reach it — and it is loud here for a reason that is not a
    # problem: several tests ask for a 404 on purpose.
    "loggers": {
        "django.request": {**LOGGING["loggers"]["django.request"], "level": "CRITICAL"},  # noqa: F405
    },
}
