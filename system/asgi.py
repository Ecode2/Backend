"""ASGI entrypoint: one process serves HTTP (DRF) and WebSocket (Channels)."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "system.settings")

# Initialise Django (and the app registry) before importing anything that
# touches models, e.g. the consumers and the WS auth middleware.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from bookshelf.ws_auth import TicketAuthMiddlewareStack  # noqa: E402
from bookshelf.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": TicketAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
