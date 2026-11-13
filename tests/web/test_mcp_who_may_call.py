import pytest
from agents.mcp_wire import MCP_ENDPOINT_PATH
from webauth.ports import AccountKind

from skat.engine.bidding import Pass
from skat.engine.deal import Position
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.mcp import AGENT_GROUP, MCP_GROUP, PLAY_CARD_TOOL
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import SUBJECT, agent_account_id
from tests.web.support.playing import card, card_body
from tests.web.support.skat import FETCH, Skat, mcp_message, stored

MIDDLEHAND = Position.MIDDLEHAND
OWNER = "the-agents-owner"


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


class TestAuctionRoutesTakeTheAgentsBearer:
    @pytest.mark.parametrize("headers", [{}, {"origin": TEST_PUBLIC_ORIGIN}], ids=["no origin", "with an origin"])
    def test_the_bearer_posts_a_marked_route_directly_as_the_agents_own_account(
        self, skat, issuer, agent, middlehand_auction, headers
    ):
        table = middlehand_auction
        token = issuer.agent_token(SUBJECT)

        answer = skat.client.post(
            f"{TABLES_PATH}/{table.table_id}{TABLE_AUCTION_PASS_SUFFIX}",
            json={"command_id": "agent-step-direct", "version": table.record.version},
            headers={"authorization": f"Bearer {token}", **FETCH, **headers},
        )

        assert answer.status_code == 200, answer.text
        assert table.record.progress.auction == (Pass(MIDDLEHAND),)
        assert (agent_account_id(skat), "agent-step-direct") in skat.store.receipts

    @pytest.mark.parametrize(
        "token_changes",
        [
            pytest.param({"aud": "https://elsewhere.test.invalid/mcp"}, id="wrong audience"),
            pytest.param({"scope": "another-scope"}, id="missing scope"),
            pytest.param({"groups": [AGENT_GROUP]}, id="no mcp group"),
            pytest.param({"iat": 0, "exp": 1}, id="expired"),
        ],
    )
    def test_a_token_that_does_not_fit_is_refused_at_the_route_and_nothing_runs(
        self, skat, issuer, middlehand_auction, token_changes
    ):
        table = middlehand_auction
        before = stored(skat)
        token = issuer.agent_token(SUBJECT, **token_changes)

        answer = skat.client.post(
            f"{TABLES_PATH}/{table.table_id}{TABLE_AUCTION_PASS_SUFFIX}",
            json={"command_id": "agent-step-direct", "version": table.record.version},
            headers={"authorization": f"Bearer {token}", **FETCH},
        )

        assert answer.status_code in {401, 403}
        assert stored(skat) == before


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
            pytest.param("POST", "/auction", {"action": "pass", "version": 1}, id="the auction path without a step"),
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
            f"{TABLES_PATH}/{forehand_table.table_id}{suffix}",
            json=None if body is None else {"command_id": "agent-move-0099", **body},
            headers={"authorization": f"Bearer {token}", "origin": TEST_PUBLIC_ORIGIN, **FETCH},
        )

        assert answer.status_code in {401, 403}
        assert stored(skat) == before
