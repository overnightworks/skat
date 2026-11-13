import json
from contextlib import contextmanager
from dataclasses import dataclass

from agents.mcp_wire import MCP_ENDPOINT_PATH
from agents.member import ACCEPT_INVITATION_TOOL, STANDING_URI, PlaceRef, place_view_uri, place_window_uri

from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.mcp import OPEN_TABLE_TOOL, PLAY_CARD_TOOL, READ_TABLE_TOOL, SIT_DOWN_TOOL, STAND_UP_TOOL
from skat.web.tables import TABLES_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import card_body
from tests.web.support.skat import mcp_message

SUBJECT = "agent-subject"
ACKNOWLEDGED = "notifications/subscriptions/acknowledged"
UPDATED = "notifications/resources/updated"


def agent_account_id(skat):
    return skat.stores.accounts.get(SUBJECT).id


def view_uri_of(table_id):
    """The resource a seated agent reads its table through."""
    return place_view_uri(PlaceRef(kind="table", id=table_id))


def window_uri_of(table_id):
    """The resource a seated agent reads what happened at its table through."""
    return place_window_uri(PlaceRef(kind="table", id=table_id))


@dataclass(frozen=True)
class ToolAnswer:
    """What a tool call gave back: whether it failed, and the text the route answered."""

    is_error: bool
    text: str

    def json(self):
        return json.loads(self.text)


class Agent:
    """An agent's client against the app in this process: a token of its own at every request."""

    def __init__(self, skat, issuer, subject=SUBJECT, **claims):
        self.skat = skat
        self.issuer = issuer
        self.subject = subject
        self.claims = claims

    def request(self, method, params=None, *, token_changes=None, extra_headers=None):
        headers, body = mcp_message(method, params)
        token = self.issuer.agent_token(self.subject, **{**self.claims, **(token_changes or {})})
        self.skat.client.cookies.clear()
        return self.skat.client.post(
            MCP_ENDPOINT_PATH,
            json=body,
            headers={"authorization": f"Bearer {token}", **headers, **(extra_headers or {})},
        )

    @contextmanager
    def listening(self):
        """A `subscriptions/listen` stream on the agent's standing; yields its frames, the acknowledgement read."""
        headers, body = mcp_message(
            "subscriptions/listen", {"notifications": {"resourceSubscriptions": [STANDING_URI]}}
        )
        token = self.issuer.agent_token(self.subject, **self.claims)
        self.skat.client.cookies.clear()
        with self.skat.client.stream(
            "POST", MCP_ENDPOINT_PATH, json=body, headers={"authorization": f"Bearer {token}", **headers}
        ) as stream:
            frames = (
                json.loads(line.removeprefix("data: ")) for line in stream.iter_lines() if line.startswith("data: ")
            )
            assert next(frames)["method"] == ACKNOWLEDGED
            yield frames

    def call(self, tool, **arguments):
        answer = self.request("tools/call", {"name": tool, "arguments": arguments})
        assert answer.status_code == 200, answer.text
        result = answer.json()["result"]
        return ToolAnswer(result.get("isError", False), result["content"][0]["text"])

    def read(self, table_id):
        return self.call(READ_TABLE_TOOL, table_id=table_id)

    def standing(self):
        """The standing as the agent reads it: the answer's text, the whole of what the agent is shown."""
        answer = self.request("resources/read", {"uri": STANDING_URI})
        assert answer.status_code == 200, answer.text
        return answer.json()["result"]["contents"][0]["text"]

    def read_resource(self, uri):
        """The answer of `resources/read` as it came, for a resource that may be unknown."""
        return self.request("resources/read", {"uri": uri})

    def view(self, table_id):
        """The agent's view of its table, as a runner reads it: revision, awaits_you and state."""
        answer = self.read_resource(view_uri_of(table_id))
        assert answer.status_code == 200, answer.text
        return json.loads(answer.json()["result"]["contents"][0]["text"])

    def listed_resources(self):
        answer = self.request("resources/list")
        assert answer.status_code == 200, answer.text
        return [resource["uri"] for resource in answer.json()["result"]["resources"]]

    def accept(self, table_id, offer, **changes):
        """`accept_invitation` for the offer's id and epoch; a change replaces one argument."""
        arguments = {
            "place": {"kind": "table", "id": table_id},
            "invitation": offer.id,
            "epoch": offer.epoch,
            **changes,
        }
        return self.call(ACCEPT_INVITATION_TOOL, **arguments)

    def open_table(self, *, command_id="agent-open-0001", series_length=36, **changes):
        return self.call(OPEN_TABLE_TOOL, command_id=command_id, series_length=series_length, **changes)

    def sit_down(self, table_id, seat, *, command_id="agent-sit-0001"):
        return self.call(SIT_DOWN_TOOL, table_id=table_id, seat=seat, command_id=command_id)

    def stand_up(self, table_id, *, command_id="agent-stand-0001"):
        return self.call(STAND_UP_TOOL, table_id=table_id, command_id=command_id)

    def play(self, table, played, *, command_id="agent-move-0001", **changes):
        return self.call(
            PLAY_CARD_TOOL,
            table_id=table.table_id,
            command_id=command_id,
            **{"version": table.record.version, **card_body(played), **changes},
        )

    def take_step(self, tool, table, *, command_id="agent-step-0001", **changes):
        return self.call(
            tool, table_id=table.table_id, command_id=command_id, **{"version": table.record.version, **changes}
        )

    def admitted(self):
        """The first call, which creates the agent's account; returns the headers of a cookie session for it."""
        assert self.request("tools/list").status_code == 200
        return self.skat.member(self.skat.stores.accounts.get(self.subject))[0]


def person_steps(table, position, suffix):
    """The person at `position` takes an auction step through its route with a cookie session."""
    answer = table.skat.client.post(
        f"{TABLES_PATH}/{table.table_id}{suffix}",
        json={"command_id": table.fresh_id(), "version": table.record.version},
        headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[position]},
    )
    assert answer.status_code == 200, answer.text
    table.skat.client.cookies.clear()


def person_posts(table, suffix, position, **body):
    """The person at `position` posts an act without a version through its route with a cookie session."""
    table.skat.client.cookies.clear()
    answer = table.skat.client.post(
        f"{TABLES_PATH}/{table.table_id}{suffix}",
        json={"command_id": table.fresh_id(), **body},
        headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[position]},
    )
    assert answer.status_code == 200, answer.text
    table.skat.client.cookies.clear()


def person_passes(table, position):
    person_steps(table, position, TABLE_AUCTION_PASS_SUFFIX)
