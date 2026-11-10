import http.client
import itertools
import json
from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest
from agents.mcp_wire import MCP_ENDPOINT_PATH

from tests.e2e.support.raw_http import self_signed_tolerant_context
from tests.e2e.support.server import LOOPBACK_HOST
from tests.support.signed_in import parsed_set_cookies
from tests.web.support.skat import mcp_message

if TYPE_CHECKING:
    from webauth.config import WebAuthConfig

    from tests.e2e.support.server import RunningServer

# Every e2e person gets an address of their own from this private range, as behind a proxy.
PERSON_ADDRESS_BASE = IPv4Address("10.0.0.0")
person_address_offsets = itertools.count(1)

DESKTOP = {"viewport": {"width": 1280, "height": 800}}
PHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}

SMALL_PHONE = {"viewport": {"width": 360, "height": 740}, "is_mobile": True, "has_touch": True}

FORM_FACTORS = [pytest.param(DESKTOP, id="desktop"), pytest.param(PHONE, id="phone")]
WIDTHS = [pytest.param(SMALL_PHONE, id="360"), pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1280")]


def playwright_cookie(set_cookie_header: str, config: WebAuthConfig, domain: str = LOOPBACK_HOST) -> dict[str, Any]:
    ((name, morsel),) = parsed_set_cookies([set_cookie_header])
    expires = int(config.wall_clock()) + int(morsel["max-age"])
    # The URL form of add_cookies is refused for a __Host- name, so the cookie goes in by domain and path.
    return {
        "name": name,
        "value": morsel.value,
        "domain": domain,
        "path": morsel["path"],
        "secure": bool(morsel["secure"]),
        "httpOnly": bool(morsel["httponly"]),
        "sameSite": morsel["samesite"].capitalize(),
        "expires": expires,
    }


class McpAgent:
    """A scripted MCP client of a running Skat: an agent's own token at every request, from an address of its own."""

    def __init__(self, server: RunningServer, subject: str) -> None:
        self._server = server
        self.subject = subject
        self._address = str(PERSON_ADDRESS_BASE + next(person_address_offsets))

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """The result of one JSON-RPC request."""
        headers, body = mcp_message(method, params)
        parts = urlsplit(self._server.base_url)
        connection = http.client.HTTPSConnection(
            parts.hostname or "", parts.port, context=self_signed_tolerant_context()
        )
        connection.request(
            "POST",
            MCP_ENDPOINT_PATH,
            body=json.dumps(body),
            headers={
                "authorization": f"Bearer {self._server.issuer.agent_token(self.subject)}",
                "accept": "application/json, text/event-stream",
                "content-type": "application/json",
                "x-forwarded-for": self._address,
                **headers,
            },
        )
        answer = connection.getresponse()
        text = answer.read().decode()
        connection.close()
        assert answer.status == http.HTTPStatus.OK, text
        return json.loads(text)["result"]

    def call(self, tool: str, **arguments: object) -> tuple[bool, str]:
        """Whether the tool failed, and the text it answered."""
        result = self.request("tools/call", {"name": tool, "arguments": arguments})
        return result.get("isError", False), result["content"][0]["text"]
