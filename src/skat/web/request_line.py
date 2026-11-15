"""What Skat tells the log about each request: the signed-in person and the client address for the request line, and the
reason of a refused request.

The first two decisions are webauth's (the session gate admits the person, the trusted proxies name the client); this
module only hands the answers to logline, which writes the line. logline's line names a request refused by its status
alone and as `ok`, so a refusal writes a line of its own here.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from http import HTTPStatus
from typing import TYPE_CHECKING, Final

from logline import set_client_ip, set_sub
from starlette.requests import HTTPConnection
from webauth.middleware import admitted_user
from webauth.proxies import resolve_client_ip

from skat.table.records import TableId

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

_LOGGER = logging.getLogger(__name__)
_TABLE_ID_PARAMETER: Final = "table_id"


class RequestRefusal(StrEnum):
    """Why a request was refused: the one set of `reason`s of the `request.refused` line."""

    NOT_SIGNED_IN = "not-signed-in"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not-found"
    METHOD_NOT_ALLOWED = "method-not-allowed"
    INVALID_REQUEST = "invalid-request"
    RATE_LIMITED = "rate-limited"


# A command's own refusal answers 409 and is written by its `table_command.ended` line.
_REFUSAL_OF_STATUS: Final[dict[int, RequestRefusal]] = {
    HTTPStatus.UNAUTHORIZED: RequestRefusal.NOT_SIGNED_IN,
    HTTPStatus.FORBIDDEN: RequestRefusal.FORBIDDEN,
    HTTPStatus.NOT_FOUND: RequestRefusal.NOT_FOUND,
    HTTPStatus.METHOD_NOT_ALLOWED: RequestRefusal.METHOD_NOT_ALLOWED,
    HTTPStatus.UNPROCESSABLE_ENTITY: RequestRefusal.INVALID_REQUEST,
    HTTPStatus.TOO_MANY_REQUESTS: RequestRefusal.RATE_LIMITED,
}


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


class RefusalNoting:
    """Pure ASGI middleware outside the library stack, so a request the library refuses leaves its refusal too.

    The line is written on the request's trace, with the table's id when the matched route names a table.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_noting_refusal(message: Message) -> None:
            if message["type"] == "http.response.start":
                refusal = _REFUSAL_OF_STATUS.get(message["status"])
                if refusal is not None:
                    _write_refusal(scope, refusal)
            await send(message)

        await self._app(scope, receive, send_noting_refusal if scope["type"] == "http" else send)


def _write_refusal(scope: Scope, refusal: RequestRefusal) -> None:
    named = scope.get("path_params", {}).get(_TABLE_ID_PARAMETER)
    table = None if named is None else TableId.parse(named)
    _LOGGER.info("request.refused", extra={"reason": refusal.value, "table_id": None if table is None else table.value})
