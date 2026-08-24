"""One-time signed ticket auth for the audio WebSocket.

Browsers can't set Authorization headers on WebSockets, and long-lived access
tokens leak through query strings/logs. Instead the client calls
``POST /auth/ws-ticket/`` (JWT-authenticated) to mint a short-lived, single-use
ticket and opens ``wss://.../ws/reader/{id}/?ticket=...``.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.core.cache import cache

_SALT = "bookverse.ws.ticket"


def make_ws_ticket(user) -> str:
    """Mint a signed, timestamped ticket.

    Anonymous visitors get a ticket with ``uid: None`` so they can stream a
    *public* book. The ticket is still signed and single-use, so it is not a
    way around the access checks -- the consumer re-verifies that the book is
    public before serving anything.
    """
    uid = user.id if getattr(user, "is_authenticated", False) else None
    return signing.dumps({"uid": uid}, salt=_SALT)


def _consume_ticket(ticket: str):
    """Validate + single-use-consume a ticket.

    Returns the decoded payload, or ``None`` when the ticket is invalid,
    expired or already used. Note the payload itself is returned rather than
    the user id, because ``uid: None`` is a *valid* anonymous ticket and must
    be distinguishable from a rejected one.
    """
    ttl = getattr(settings, "WS_TICKET_TTL_SECONDS", 30)
    try:
        data = signing.loads(ticket, salt=_SALT, max_age=ttl)
    except signing.BadSignature:
        return None
    # Enforce single use: the first consumer to claim the key wins.
    claim_key = f"ws_ticket_used:{signing.Signer(salt=_SALT).signature(ticket)}"
    if not cache.add(claim_key, "1", timeout=ttl + 5):
        return None
    return data


@database_sync_to_async
def _get_user(uid):
    User = get_user_model()
    try:
        return User.objects.get(pk=uid)
    except User.DoesNotExist:
        return AnonymousUser()


class TicketAuthMiddleware:
    """ASGI middleware that resolves ``scope['user']`` from a ticket query param."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs((scope.get("query_string") or b"").decode())
        ticket = (query.get("ticket") or [None])[0]
        user = AnonymousUser()
        # `ticket_valid` separates "no/!bad ticket" from "valid anonymous
        # ticket"; only the latter may reach a public book.
        ticket_valid = False
        if ticket:
            data = _consume_ticket(ticket)
            if data is not None:
                ticket_valid = True
                uid = data.get("uid")
                if uid is not None:
                    user = await _get_user(uid)
        scope["user"] = user
        scope["ws_ticket_valid"] = ticket_valid
        return await self.app(scope, receive, send)


def TicketAuthMiddlewareStack(app):
    return TicketAuthMiddleware(app)
