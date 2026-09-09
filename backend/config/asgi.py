"""ASGI entrypoint — HTTP today, HTTP *and* WebSocket once matchmaking lands.

The realtime half of Knowdown — the global matchmaking pool, the live matchup,
the server-side answer clock — will be a Channels consumer served by uvicorn
from this module, while the API keeps running ``config.wsgi`` under gunicorn:
two deployments of one image, meeting only at Redis, so a spectator holding a
socket open cannot occupy a worker that is answering REST calls.

The router is already in place with only its ``http`` branch wired. Adding the
socket route then means adding one line here and an ``apps/matches/routing.py``,
rather than restructuring the entrypoint.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

# Must run before anything imports models: it is what populates the app registry.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),
    }
)
