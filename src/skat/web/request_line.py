"""What Skat tells the request line of each request: the signed-in person and the client address.

The two decisions are webauth's (the session gate admits the person, the trusted proxies name the client); this module
only hands the answers to logline, which writes the line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from logline import set_client_ip, set_sub
from starlette.requests import HTTPConnection
from webauth.middleware import admitted_user
from webauth.proxies import resolve_client_ip

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class ClientAddressNoting:
    """Pure ASGI middleware outside the library stack, so a request the library refuses carries its client address."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            set_client_ip(scope, resolve_client_ip(HTTPConnection(scope)))
        await self._app(scope, receive, send)


class SignedInPersonNoting:
    """Pure ASGI middleware inside the session gate, so it sees only the requests the gate admitted."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            person = admitted_user(HTTPConnection(scope))
            if person is not None:
                set_sub(scope, person.id)
        await self._app(scope, receive, send)
