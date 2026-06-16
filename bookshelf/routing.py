from django.urls import re_path

from .consumers import ReaderConsumer

websocket_urlpatterns = [
    re_path(r"ws/reader/(?P<book_id>\d+)/$", ReaderConsumer.as_asgi()),
]
