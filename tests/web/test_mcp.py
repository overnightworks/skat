import json
from dataclasses import dataclass

import pytest
from agent_runtime_client.mcp_wire import MCP_ENDPOINT_PATH
from webauth.ports import AccountKind

from skat.engine.deal import Position
from skat.engine.tricks import CardPlayed, PlayRefusal
from skat.table.records import Refusal
from skat.web.auction import TABLE_AUCTION_SUFFIX
from skat.web.declaring import TABLE_DECLARATION_SUFFIX, DeclaringAction
from skat.web.mcp import AGENT_GROUP, MCP_GROUP, PLAY_CARD_TOOL, READ_TABLE_TOOL
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_SIT_SUFFIX, TABLE_STAND_SUFFIX, TABLES_PATH
from tests.support.fake_issuer import FakeIssuer
from tests.support.payload_cards import CARDS_BY_SEAT, SKAT_CARDS, cards_in, wire_cards
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import Table, card, card_body
from tests.web.support.skat import FETCH, AgentTable, Skat, mcp_message, streams_of

FOREHAND, MIDDLEHAND = Position.FOREHAND, Position.MIDDLEHAND
SUBJECT = "agent-subject"
OWNER = "the-agents-owner"
METADATA_PATH = f"/.well-known/oauth-protected-resource{MCP_ENDPOINT_PATH}"


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

    def admitted(self):
        """The first call, which creates the agent's account; returns the headers of a cookie session for it."""
        assert self.request("tools/list").status_code == 200
        return self.skat.member(self.skat.stores.accounts.get(self.subject))[0]


@pytest.fixture
def issuer(hold):
    return FakeIssuer(hold)


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


@pytest.fixture
def agent(skat, issuer):
    return Agent(skat, issuer)


@pytest.fixture
def forehand_table(skat, agent):
    """A Hand game declared at a table where the agent holds the forehand, whose turn it is."""
    table = AgentTable(skat, agent.admitted(), FOREHAND)
    table.declared_hand_game()
    skat.client.cookies.clear()
    return table


def stored(skat):
    return skat.store.tables, skat.store.receipts


class TestTools:
    def test_an_agent_is_offered_read_table_and_play_card_and_only_read_table_is_read_only(self, agent):
        answer = agent.request("tools/list")

        tools = {tool["name"]: tool for tool in answer.json()["result"]["tools"]}
        assert set(tools) == {READ_TABLE_TOOL, PLAY_CARD_TOOL}
        assert tools[READ_TABLE_TOOL]["annotations"]["readOnlyHint"] is True
        assert "readOnlyHint" not in tools[PLAY_CARD_TOOL].get("annotations", {})

    def test_the_resource_metadata_is_public(self, skat):
        answer = skat.client.get(METADATA_PATH)

        assert answer.status_code == 200
        assert answer.json()["resource"] == f"{TEST_PUBLIC_ORIGIN}{MCP_ENDPOINT_PATH}"


class TestReadTable:
    def test_a_seated_agent_gets_the_view_of_its_own_chair_as_the_route_gives_it(self, agent, forehand_table):
        answer = agent.read(forehand_table.table_id)

        view = answer.json()
        own = wire_cards(CARDS_BY_SEAT[3])
        assert not answer.is_error
        assert cards_in(view) == own
        assert {(held["suit"], held["rank"]) for held in view["hand"]["own_cards"]} == own
        assert view["hand"]["playing"]["legal_cards"]
        assert [chair["is_mine"] for chair in view["chairs"]] == [False, False, True]
        direct = forehand_table.skat.client.get(
            f"{TABLES_PATH}/{forehand_table.table_id}", headers=forehand_table.at[FOREHAND]
        )
        assert view == direct.json()

    def test_an_agent_without_a_chair_gets_the_watchers_view_without_any_card(self, skat, agent):
        agent.admitted()
        table = Table(skat)
        table.declared_hand_game()

        view = agent.read(table.table_id).json()

        assert cards_in(view) == set()
        assert not any(chair["is_mine"] for chair in view["chairs"])

    def test_the_declarer_sees_the_skat_it_took_as_its_own_view_shows_it(self, skat, agent):
        table = AgentTable(skat, agent.admitted(), MIDDLEHAND)
        table.middlehand_wins()
        skat.client.post(
            f"{TABLES_PATH}/{table.table_id}{TABLE_DECLARATION_SUFFIX}",
            json={"command_id": "command-take", "version": table.record.version, "action": DeclaringAction.TAKE},
            headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[MIDDLEHAND]},
        )

        view = agent.read(table.table_id).json()

        assert wire_cards(SKAT_CARDS) <= cards_in(view)
        direct = skat.client.get(f"{TABLES_PATH}/{table.table_id}", headers=table.at[MIDDLEHAND])
        assert view == direct.json()

    def test_a_hand_declarer_never_sees_the_skat(self, skat, agent):
        table = AgentTable(skat, agent.admitted(), MIDDLEHAND)
        table.declared_hand_game()

        view = agent.read(table.table_id).json()

        assert wire_cards(SKAT_CARDS).isdisjoint(cards_in(view))

    def test_an_unknown_table_is_a_failed_result(self, agent):
        assert agent.read("0" * 32).is_error


class TestPlayCard:
    def test_a_legal_card_on_its_turn_lands_in_the_trick_every_viewer_sees(self, skat, agent, forehand_table):
        before = forehand_table.record.version
        with streams_of(skat, forehand_table.table_id, [(forehand_table.watcher, None)]) as (watcher,):
            answer = agent.play(forehand_table, card("S7"))

            assert not answer.is_error, answer.text
            assert answer.json()["version"] == before + 1
            assert forehand_table.plays == (CardPlayed(FOREHAND, card("S7")),)
            trick = next(view["hand"]["playing"]["current_trick"] for view in watcher if view["version"] == before + 1)
            assert [(seated["seat"], seated["card"]) for seated in trick] == [(3, card_body(card("S7")))]

    def test_the_same_call_again_answers_the_same_and_plays_nothing_twice(self, agent, forehand_table):
        first = agent.play(forehand_table, card("S7"))
        version = forehand_table.record.version

        again = agent.play(forehand_table, card("S7"), version=version - 1)

        assert (again.is_error, again.text) == (first.is_error, first.text)
        assert forehand_table.record.version == version
        assert forehand_table.plays == (CardPlayed(FOREHAND, card("S7")),)

    def test_the_same_command_id_with_another_card_is_refused_as_reused(self, agent, forehand_table):
        agent.play(forehand_table, card("S7"))
        before = stored(forehand_table.skat)

        answer = agent.play(forehand_table, card("S8"))

        assert answer.is_error
        assert "reused" in answer.text
        assert stored(forehand_table.skat) == before

    @pytest.mark.parametrize(
        ("earlier", "changes", "reason"),
        [
            pytest.param((), {"version": 0}, Refusal.STALE_VERSION, id="stale version"),
            pytest.param((), card_body(card("HA")), PlayRefusal.NOT_IN_HAND, id="card not held"),
            pytest.param(("S7",), card_body(card("S8")), PlayRefusal.NOT_YOUR_TURN, id="not its turn"),
        ],
    )
    def test_a_refused_move_is_a_failed_result_with_the_routes_reason_and_changes_nothing(
        self, agent, forehand_table, earlier, changes, reason
    ):
        for earlier_card in earlier:
            agent.play(forehand_table, card(earlier_card), command_id=f"agent-move-{earlier_card}")
        before = stored(forehand_table.skat)

        answer = agent.play(forehand_table, card("S7"), command_id="agent-move-refused", **changes)

        assert answer.is_error
        assert answer.json()["reason"] == reason
        assert stored(forehand_table.skat) == before


class TestWhoMayCall:
    @pytest.mark.parametrize(
        ("changes", "status"),
        [
            pytest.param({"groups": [AGENT_GROUP]}, 403, id="no mcp group"),
            pytest.param({"groups": [MCP_GROUP], "azp": "another-client"}, 401, id="foreign client, no agents"),
            pytest.param({"aud": "https://elsewhere.test.invalid/mcp"}, 401, id="wrong audience"),
            pytest.param({"scope": "another-scope"}, 403, id="missing scope"),
            pytest.param({"iat": 0, "exp": 1}, 401, id="expired"),
            pytest.param({"agent_name": None}, 401, id="no agent name"),
            pytest.param({"agent_owner": None}, 401, id="no agent owner"),
        ],
    )
    def test_a_token_that_does_not_fit_is_refused_and_creates_no_account(self, skat, agent, changes, status):
        answer = agent.request("tools/list", token_changes=changes)

        assert answer.status_code == status
        assert "result" not in answer.text
        assert skat.stores.accounts.get(SUBJECT) is None

    def test_the_first_call_creates_the_agents_own_account_never_its_owners(self, skat, agent):
        agent.request("tools/list", token_changes={"agent_owner": OWNER})
        agent.request("tools/list", token_changes={"agent_owner": OWNER})

        account = skat.stores.accounts.get(SUBJECT)
        assert account.kind is AccountKind.AGENT
        assert skat.stores.accounts.get(OWNER) is None

    def test_a_cookie_session_without_a_bearer_is_challenged_and_runs_nothing(self, skat, forehand_table):
        headers, body = mcp_message("tools/list")

        answer = skat.client.post(MCP_ENDPOINT_PATH, json=body, headers={**headers, **forehand_table.watcher})

        assert answer.status_code == 401
        assert "resource_metadata" in answer.headers["www-authenticate"]

    def test_a_request_with_an_origin_is_refused_and_runs_nothing(self, agent, forehand_table):
        before = stored(forehand_table.skat)

        answer = agent.request(
            "tools/call",
            {
                "name": PLAY_CARD_TOOL,
                "arguments": {
                    "table_id": forehand_table.table_id,
                    "command_id": "agent-move-origin",
                    "version": forehand_table.record.version,
                    **card_body(card("S7")),
                },
            },
            extra_headers={"origin": TEST_PUBLIC_ORIGIN},
        )

        assert answer.status_code == 403
        assert stored(forehand_table.skat) == before

    @pytest.mark.parametrize(
        ("method", "suffix", "body"),
        [
            pytest.param("POST", "", {}, id="open a table"),
            pytest.param("POST", TABLE_SIT_SUFFIX, {"seat": 1}, id="sit"),
            pytest.param("POST", TABLE_STAND_SUFFIX, {}, id="stand"),
            pytest.param("POST", TABLE_READY_SUFFIX, {"ordinal": 1}, id="ready"),
            pytest.param("POST", TABLE_AUCTION_SUFFIX, {"action": "pass", "version": 1}, id="auction"),
            pytest.param("POST", TABLE_DECLARATION_SUFFIX, {"action": "take", "version": 1}, id="declaration"),
            pytest.param("GET", TABLE_EVENTS_SUFFIX, None, id="events"),
        ],
    )
    def test_an_agent_token_is_refused_on_a_route_that_is_no_tool_and_changes_nothing(
        self, skat, issuer, forehand_table, method, suffix, body
    ):
        before = stored(skat)
        token = issuer.agent_token(SUBJECT)

        answer = skat.client.request(
            method,
            f"{TABLES_PATH}/{forehand_table.table_id}{suffix}" if suffix != "" else TABLES_PATH,
            json=None if body is None else {"command_id": "agent-move-0099", **body},
            headers={"authorization": f"Bearer {token}", "origin": TEST_PUBLIC_ORIGIN, **FETCH},
        )

        assert answer.status_code in {401, 403}
        assert stored(skat) == before
