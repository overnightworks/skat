import json
from dataclasses import dataclass

from agent_runtime_client.mcp_wire import MCP_ENDPOINT_PATH

from skat.web.mcp import PLAY_CARD_TOOL, READ_TABLE_TOOL
from tests.web.support.playing import card_body
from tests.web.support.skat import mcp_message

SUBJECT = "agent-subject"


@dataclass(frozen=True)
class ToolAnswer:
    """What a tool call gave back: whether it failed, and the text the route answered."""

    is_error: bool
    text: str

    def json(self):
        return json.loads(self.text)


class Agent:
    """An agent's client against the app in this process: a token of its own at every request."""

    def __init__(self, skat, issuer, subject=SUBJECT):
        self.skat = skat
        self.issuer = issuer
        self.subject = subject

    def request(self, method, params=None, *, token_changes=None, extra_headers=None):
        headers, body = mcp_message(method, params)
        token = self.issuer.agent_token(self.subject, **(token_changes or {}))
        self.skat.client.cookies.clear()
        return self.skat.client.post(
            MCP_ENDPOINT_PATH,
            json=body,
            headers={"authorization": f"Bearer {token}", **headers, **(extra_headers or {})},
        )

    def call(self, tool, **arguments):
        answer = self.request("tools/call", {"name": tool, "arguments": arguments})
        assert answer.status_code == 200, answer.text
        result = answer.json()["result"]
        return ToolAnswer(result.get("isError", False), result["content"][0]["text"])

    def read(self, table_id):
        return self.call(READ_TABLE_TOOL, table_id=table_id)

    def play(self, table, played, *, command_id="agent-move-0001", **changes):
        return self.call(
            PLAY_CARD_TOOL,
            table_id=table.table_id,
            command_id=command_id,
            **{"version": table.record.version, **card_body(played), **changes},
        )

    def auction_step(self, tool, table, *, command_id="agent-step-0001", **changes):
        return self.call(
            tool, table_id=table.table_id, command_id=command_id, **{"version": table.record.version, **changes}
        )

    def admitted(self):
        """The first call, which creates the agent's account; returns the headers of a cookie session for it."""
        assert self.request("tools/list").status_code == 200
        return self.skat.member(self.skat.stores.accounts.get(self.subject))[0]
