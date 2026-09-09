#!/usr/bin/env bash
#
# Scaffold a new domain app with the layered layout every app here uses.
#
# The backend already exists — this is not a one-time generator. Run it to add an
# app, or re-run it to fill in a directory somebody left out: it creates nothing
# that is already there, so it is safe on a live tree.
#
#     ./scripts/bootstrap_backend.sh                 # every app in APPS below
#     ./scripts/bootstrap_backend.sh leaderboards    # just this one
#
# It does NOT edit settings. Add the new app to LOCAL_APPS in
# backend/config/settings/base.py and, once it serves HTTP, include its
# api/urls.py in config/urls.py.

set -euo pipefail

BACKEND_DIR="backend"

# The apps that exist today. Listed so a fresh checkout can be re-scaffolded and
# so the set is written down somewhere other than a settings file.
APPS=(
  core_common
  accounts
  players
  categories
  questions
  matches
  rankings
  achievements
)

if [ $# -gt 0 ]; then
  APPS=("$@")
fi

if ! uv run python -c "import django" >/dev/null 2>&1; then
    echo "Django is not installed. Run: uv sync"
    exit 1
fi

for app in "${APPS[@]}"; do
    APP_PATH="$BACKEND_DIR/apps/$app"

    if [ ! -d "$APP_PATH" ]; then
        echo "Creating $app..."
        mkdir -p "$APP_PATH"
        uv run python "$BACKEND_DIR/manage.py" startapp "$app" "$APP_PATH"
    else
        echo "Filling in $app..."
    fi

    # The layers. Packages rather than modules from the start: every one of these
    # grows past a single file, and splitting one later means touching every
    # import that named it.
    for layer in api services selectors schemas permissions validators migrations; do
        mkdir -p "$APP_PATH/$layer"
        touch "$APP_PATH/$layer/__init__.py"
    done

    touch "$APP_PATH/api/views.py" "$APP_PATH/api/serializers.py" "$APP_PATH/api/urls.py"
done

mkdir -p "$BACKEND_DIR/static" "$BACKEND_DIR/templates" "$BACKEND_DIR/media"

echo
echo "Done. Next:"
echo "  - add apps.<name> to LOCAL_APPS in backend/config/settings/base.py"
echo "  - include its api/urls.py in backend/config/urls.py when it serves HTTP"
