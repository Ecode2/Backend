from django.urls import re_path

from .consumers import ReaderConsumer

# Book ids are UUIDs, so the old \d+ pattern matched nothing and Channels
# raised "No route found for path ...", surfacing as an HTTP 500 on the
# WebSocket handshake.
UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

websocket_urlpatterns = [
    re_path(rf"ws/reader/(?P<book_id>{UUID_RE})/$", ReaderConsumer.as_asgi()),
]
