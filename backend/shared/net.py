"""Client IP resolution behind a reverse proxy chain.

``X-Forwarded-For`` is a chain each proxy *appends* to: leftmost is the original
client, each entry after it is one hop closer to us. The header is also just a
string a caller can send — nothing stops a browser from sending
``X-Forwarded-For: 1.2.3.4`` itself — so it can only be trusted as many hops deep
as there are proxies in front of Django known to append to it honestly.
``settings.TRUSTED_PROXY_HOPS`` is that count, and it is 0 by default: behind a
cluster ingress every request tends to arrive NAT'd through the same few internal
hops, so trusting the header blind would log every visitor as the gateway rather
than as themselves. Raise the count only once the real chain in front of a given
deployment has been confirmed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest


def _resolve(*, peer: str, forwarded_for: str, trusted_hops: int) -> str:
    if trusted_hops <= 0:
        return peer
    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    if len(hops) < trusted_hops:
        # Fewer hops than we are told to trust — the header was short-circuited
        # (or never set), so fall back to the socket peer rather than guess.
        return peer
    return hops[-trusted_hops]


def client_ip(request: HttpRequest, *, trusted_hops: int) -> str:
    """The address of whoever actually made this request, for a Django view."""
    return _resolve(
        peer=request.META.get("REMOTE_ADDR", "") or "",
        forwarded_for=request.META.get("HTTP_X_FORWARDED_FOR", ""),
        trusted_hops=trusted_hops,
    )


def client_ip_from_scope(scope: dict, *, trusted_hops: int) -> str:
    """The same resolution for an ASGI (WebSocket) connection.

    Channels hands headers as a list of ``(name_bytes, value_bytes)`` pairs
    rather than Django's ``request.META``, and the socket's peer address as
    ``scope["client"]`` — a ``(host, port)`` pair, or ``None`` for a transport
    with no notion of one. Unused until the matchmaking consumer lands; it sits
    here now so the socket and the request answer "who is this" the same way.
    """
    client = scope.get("client")
    peer = client[0] if client else ""
    forwarded_for = ""
    for name, value in scope.get("headers", ()):
        if name == b"x-forwarded-for":
            forwarded_for = value.decode("latin-1")
            break
    return _resolve(peer=peer, forwarded_for=forwarded_for, trusted_hops=trusted_hops)
