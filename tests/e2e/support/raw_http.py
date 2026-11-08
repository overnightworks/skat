import http.client
import json
import ssl
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from tests.support.signed_in import cookie_header

if TYPE_CHECKING:
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember


def self_signed_tolerant_context() -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


class RawSession:
    """One signed-in member's raw HTTP traffic with a running Skat; every body that came back is kept as text."""

    def __init__(self, server: RunningServer, member: SeededMember) -> None:
        parts = urlsplit(server.base_url)
        self._host, self._port = parts.hostname or "", parts.port
        self._origin = server.base_url
        self._cookie = cookie_header(member.set_cookie_headers)
        self.member = member
        self.bodies: list[str] = []

    def _connect(self) -> http.client.HTTPSConnection:
        return http.client.HTTPSConnection(self._host, self._port, context=self_signed_tolerant_context())

    def _headers(self) -> dict[str, str]:
        return {"cookie": self._cookie, "origin": self._origin, "accept": "application/json"}

    def get(self, path: str) -> str:
        return self._answer("GET", path, None)

    def post(self, path: str, body: dict[str, object]) -> str:
        return self._answer("POST", path, json.dumps(body))

    def _answer(self, method: str, path: str, body: str | None) -> str:
        connection = self._connect()
        headers = self._headers() if body is None else {**self._headers(), "content-type": "application/json"}
        connection.request(method, path, body=body, headers=headers)
        text = connection.getresponse().read().decode()
        connection.close()
        self.bodies.append(text)
        return text

    def first_stream_message(self, path: str) -> None:
        """Open the event stream, keep its first message and close it."""
        connection = self._connect()
        connection.request("GET", path, headers=self._headers())
        response = connection.getresponse()
        self.bodies.append(response.readline().decode())
        connection.close()
