# syntax=docker/dockerfile:1
#
# Backend (Django) image — build context is the REPOSITORY ROOT (pyproject.toml
# and uv.lock live there; the Django project lives in backend/):
#
#   docker build -f backend/Dockerfile -t <registry>/knowdown-backend:dev .
#
# Multi-stage: uv resolves deps into an isolated venv in the builder; only that
# venv + the app source land in the slim, non-root runtime — no compilers, no
# uv, no caches in the shipped image.

########################  builder  ########################
FROM ghcr.io/astral-sh/uv:0.9-python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# 1) Dependency layer — cached until pyproject.toml/uv.lock change.
#    --no-install-project: only third-party deps here; app source is copied into
#    the runtime stage, so a code change never busts the dependency cache.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# 2) The servers. Neither is an app dependency — local dev's `runserver` uses
#    Daphne (already in INSTALLED_APPS for that reason) — so both go into the
#    same venv here instead: one image runs either role, picked by
#    SERVER_MODE in entrypoint.sh: gunicorn/WSGI for /api/, uvicorn/ASGI for
#    /ws/. Channels itself IS an app dependency (app code imports it) and so
#    comes in via the layer above.
# Pin gunicorn 23.x: gunicorn 26 adds a "control server" that writes a socket
# into the (read-only) code dir and errors on every boot; 23.0.0 needs none.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install "gunicorn==23.0.0" "uvicorn[standard]==0.38.0"

########################  runtime  ########################
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    # Import the app via PYTHONPATH so gunicorn can run from a writable cwd
    # (/data) while the code dir /app stays read-only.
    PYTHONPATH=/app \
    # Default to the hardened settings; a staging overlay can override this.
    # `docker run` with no SECRET_KEY fails closed (config/settings/production.py).
    DJANGO_SETTINGS_MODULE=config.settings.production \
    # api (gunicorn/wsgi) or realtime (uvicorn/asgi) — see entrypoint.sh.
    SERVER_MODE=api

# Run as an unprivileged user, never root.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

# Resolved venv from the builder, then the Django project (manage.py, config/,
# apps/ …). App source lives at /app so `config.wsgi` is importable directly.
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app backend/ /app/

# Collect the Django admin's static files into STATIC_ROOT (/app/staticfiles)
# so WhiteNoise can serve them from gunicorn — the admin without its CSS is
# unusable, and the SPA never sees these paths (they answer under
# /_ops/static/ when the admin gate is on, routed straight at the backend).
#
# At BUILD time, and as root, because /app is root-owned and read-only at
# runtime by design — doing this at startup would either hit PermissionError
# or write into a filesystem the app container cannot see. Nothing here
# touches the database; the dummy values only satisfy production settings'
# fail-closed checks for the duration of this one command.
RUN SECRET_KEY=build-only ALLOWED_HOSTS=localhost \
    python /app/manage.py collectstatic --noinput --clear

# The code dir stays root-owned / read-only. Runtime-writable state (a
# fallback sqlite file, if no external DATABASE_URL is provided; question
# images, if MEDIA_ROOT is left at its default — see step 23) lives here
# instead.
RUN mkdir -p /data && chown app:app /data
VOLUME ["/data"]

USER app
EXPOSE 8080

# Liveness at the image level too (the orchestrator has its own probes). Uses
# stdlib only. Deliberately the *process-only* endpoint: an unreachable
# database must not make a working container report itself dead — see
# apps.core_common.api.views.LivenessView.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health/live/', timeout=2).status==200 else sys.exit(1)"]

ENTRYPOINT ["/app/entrypoint.sh"]
