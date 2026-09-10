#!/bin/sh
# Container entrypoint for the Django backend.
#
# One image, two roles, chosen with SERVER_MODE:
#
#   api      (default) gunicorn on config.wsgi  — serves /api/, threaded workers
#   realtime           uvicorn  on config.asgi  — serves /ws/, holds the sockets
#
# They are separate deployments that meet only at Redis (see
# apps.matches.publish / apps.matches.pool). Keeping them in one image means
# the consumer and the services that feed it can never be built from
# different commits; keeping them in separate processes means a spectator
# holding a socket open cannot occupy an API worker, which is precisely what
# a sync WSGI server cannot survive.
#
# Applies migrations, then hands off (exec) to the server as PID 1 so signals
# and graceful shutdown work.
#
# Under an orchestrator that supports init containers, prefer running
# `migrate_locked` there instead and set RUN_MIGRATIONS=0 on the deployment —
# the schema should be current before the first request can arrive, not on
# the way to serving it. This path remains for running the image directly
# (`docker run`, a one-off container, a platform with no init-container
# concept), where there is no other place to do it.
set -eu

SERVER_MODE="${SERVER_MODE:-api}"

# Only the api role migrates. The realtime process rolls independently and
# would otherwise race the api process for the same lock on every restart.
#
# migrate_locked, not migrate: it takes a Postgres advisory lock first, so
# replicas that start together serialise instead of both applying the same
# migration. That is what makes this safe to leave enabled by default even
# though 'only one process ever runs this' is no longer true with replicas>1.
if [ "$SERVER_MODE" = "api" ] && [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "==> applying database migrations"
    python manage.py migrate_locked
fi

# Both servers run from the writable /data dir (code dir /app is read-only);
# PYTHONPATH=/app keeps `config.wsgi` / `config.asgi` importable. Django uses
# absolute BASE_DIR paths, so cwd does not affect templates/static resolution.
cd /data

case "$SERVER_MODE" in
    api)
        # gthread, not sync. This workload is DB-I/O bound: a request spends most
        # of its life waiting on Postgres, and a *sync* worker serves nothing
        # else while it waits — N workers meant N concurrent requests, so one
        # slow list query stalled a whole worker's slice of capacity. Threads
        # let a worker pick up the next request while the first blocks on I/O.
        # Workers still exist as separate processes to get past the GIL for the
        # little CPU-bound work there is.
        #
        # --max-requests recycles each worker periodically so a leak in any one
        # of them is bounded; the jitter keeps all workers from recycling in
        # step. --worker-tmp-dir /dev/shm puts gunicorn's heartbeat file on
        # tmpfs — on a disk-backed /tmp a slow write gets a *healthy* worker
        # killed as unresponsive.
        echo "==> starting gunicorn (wsgi) on :8080"
        exec gunicorn config.wsgi:application \
            --bind "0.0.0.0:8080" \
            --worker-class "${GUNICORN_WORKER_CLASS:-gthread}" \
            --workers "${GUNICORN_WORKERS:-3}" \
            --threads "${GUNICORN_THREADS:-8}" \
            --timeout "${GUNICORN_TIMEOUT:-60}" \
            --max-requests "${GUNICORN_MAX_REQUESTS:-1000}" \
            --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER:-100}" \
            --worker-tmp-dir /dev/shm \
            --access-logfile - \
            --error-logfile -
        ;;
    realtime)
        # Sockets are cheap to hold and expensive to drop, so this scales by
        # concurrency (async, one process) rather than by worker count. Redis is
        # what makes several replicas of it equivalent to one — see
        # apps.matches.pool and apps.matches.presence.
        echo "==> starting uvicorn (asgi) on :8080"
        exec uvicorn config.asgi:application \
            --host "0.0.0.0" \
            --port 8080 \
            --workers "${UVICORN_WORKERS:-1}" \
            --proxy-headers \
            --forwarded-allow-ips "*" \
            --log-level "${UVICORN_LOG_LEVEL:-info}"
        ;;
    *)
        echo "FATAL: unknown SERVER_MODE '$SERVER_MODE' (expected 'api' or 'realtime')" >&2
        exit 64
        ;;
esac
