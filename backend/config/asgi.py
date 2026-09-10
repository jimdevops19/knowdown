"""ASGI entrypoint — HTTP and WebSocket.

The realtime half of Knowdown — the global matchmaking pool, the live matchup,
the server-side answer clock — is ``apps.matches``' Channels consumers, served
by uvicorn from this module (``SERVER_MODE=realtime``), while the API keeps
running ``config.wsgi`` under gunicorn (``SERVER_MODE=api``): two deployments
of one image, meeting only at Redis, so a spectator holding a socket open
cannot occupy a worker that is answering REST calls.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

# Must run before anything imports models: it is what populates the app registry.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.matches.authentication import JWTAuthMiddlewareStack  # noqa: E402
from apps.matches.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
