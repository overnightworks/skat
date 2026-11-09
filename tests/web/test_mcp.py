import copy

import pytest
from agent_runtime_client.mcp_wire import MCP_ENDPOINT_PATH
from webauth.ports import AccountKind

from skat.engine.bidding import VALID_BIDS, Awaiting, Bid, BidRefusal, Declared, Hold, Pass
from skat.engine.deal import Position, seats_from
from skat.engine.tricks import CardPlayed, PlayRefusal
from skat.table.auction import AuctionAction
from skat.table.hand_state import auction_of
from skat.table.records import Refusal
from skat.web.auction import TABLE_AUCTION_HOLD_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.declaring import TABLE_DECLARATION_SUFFIX, DeclaringAction
from skat.web.mcp import (
    AGENT_GROUP,
    AUCTION_BID_TOOL,
    AUCTION_HOLD_TOOL,
    AUCTION_PASS_TOOL,
    AUCTION_PLAY_TOOL,
    CONTINUE_AFTER_RESULT_TOOL,
    MCP_GROUP,
    PLAY_CARD_TOOL,
    READ_TABLE_TOOL,
)
from skat.web.tables import (
    TABLE_EVENTS_SUFFIX,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
    TABLES_PATH,
    AwaitingToken,
)
from tests.support.payload_cards import CARDS_BY_SEAT, DEALER_SEAT, SKAT_CARDS, cards_in, wire_cards
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import SUBJECT
from tests.web.support.playing import Table, card, card_body
from tests.web.support.skat import FETCH, UNKNOWN_ID, AgentTable, Skat, mcp_message, streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
AUCTION_TOOLS = {AUCTION_BID_TOOL, AUCTION_HOLD_TOOL, AUCTION_PASS_TOOL, AUCTION_PLAY_TOOL}
OWNER = "the-agents-owner"
METADATA_PATH = f"/.well-known/oauth-protected-resource{MCP_ENDPOINT_PATH}"


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


@pytest.fixture
def middlehand_auction(skat, agent):
    """A dealt table, no step taken yet, where the agent holds the middlehand chair, whose turn it is."""
    table = AgentTable(skat, agent.admitted(), MIDDLEHAND)
    skat.client.cookies.clear()
    return table


@pytest.fixture
def forehand_auction(skat, agent):
    """A dealt table, no step taken yet, where the agent holds the forehand chair."""
    table = AgentTable(skat, agent.admitted(), FOREHAND)
    skat.client.cookies.clear()
    return table


@pytest.fixture
def forehand_table(skat, agent):
    """A Hand game declared at a table where the agent holds the forehand, whose turn it is."""
    table = AgentTable(skat, agent.admitted(), FOREHAND)
    table.declared_hand_game()
    skat.client.cookies.clear()
    return table


def person_steps(table, position, suffix):
    answer = table.skat.client.post(
        f"{TABLES_PATH}/{table.table_id}{suffix}",
        json={"command_id": table.fresh_id(), "version": table.record.version},
        headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[position]},
    )
    assert answer.status_code == 200, answer.text
    table.skat.client.cookies.clear()


def person_passes(table, position):
    person_steps(table, position, TABLE_AUCTION_PASS_SUFFIX)


def agent_account_id(skat):
    return skat.stores.accounts.get(SUBJECT).id


def stored(skat):
    return copy.deepcopy((skat.store.tables, skat.store.receipts))


class TestTools:
    def test_an_agent_is_offered_the_table_tools_and_only_read_table_is_read_only(self, agent):
        answer = agent.request("tools/list")

        tools = {tool["name"]: tool for tool in answer.json()["result"]["tools"]}
        assert set(tools) == {READ_TABLE_TOOL, PLAY_CARD_TOOL, CONTINUE_AFTER_RESULT_TOOL} | AUCTION_TOOLS
        assert tools[READ_TABLE_TOOL]["annotations"]["readOnlyHint"] is True
        for name in set(tools) - {READ_TABLE_TOOL}:
            assert "readOnlyHint" not in tools[name].get("annotations", {})

    def test_each_auction_tool_has_a_description_of_its_own(self, agent):
        answer = agent.request("tools/list")

        tools = {tool["name"]: tool for tool in answer.json()["result"]["tools"]}
        descriptions = {tools[name]["description"] for name in AUCTION_TOOLS}
        assert len(descriptions) == len(AUCTION_TOOLS)

    @pytest.mark.parametrize(
        ("tool", "token"),
        [
            pytest.param(AUCTION_BID_TOOL, AwaitingToken.BID, id="bid"),
            pytest.param(AUCTION_HOLD_TOOL, AwaitingToken.ANSWER, id="hold"),
            pytest.param(AUCTION_PLAY_TOOL, AwaitingToken.PLAY, id="play"),
        ],
    )
    def test_a_tool_description_names_the_awaiting_value_its_step_fits(self, agent, tool, token):
        answer = agent.request("tools/list")

        tools = {listed["name"]: listed for listed in answer.json()["result"]["tools"]}
        assert f'is "{token.value}"' in tools[tool]["description"]

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

    def test_the_series_of_a_table_reads_at_the_tool_as_the_route_gives_it(self, skat, agent):
        headers = agent.admitted()
        table_id = skat.create(headers, series_length=12).json()["id"]

        view = agent.read(table_id).json()

        assert view["series"] == {"game_number": 0, "game_count": 12, "over": False}
        assert view == skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers).json()

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
        assert agent.read(UNKNOWN_ID).is_error


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
    def test_a_refused_move_is_a_failed_result_with_the_routes_reason_and_leaves_the_table_unchanged(
        self, agent, forehand_table, earlier, changes, reason
    ):
        for earlier_card in earlier:
            agent.play(forehand_table, card(earlier_card), command_id=f"agent-move-{earlier_card}")
        before = stored(forehand_table.skat)

        answer = agent.play(forehand_table, card("S7"), command_id="agent-move-refused", **changes)

        assert answer.is_error
        assert answer.json()["reason"] == reason
        assert stored(forehand_table.skat)[0] == before[0]


class TestAuctionSteps:
    def test_a_bid_from_the_offered_values_is_stored_for_the_agents_seat_and_every_viewer_sees_it(
        self, skat, agent, middlehand_auction
    ):
        table = middlehand_auction
        value = VALID_BIDS[0]
        before = table.record.version
        with streams_of(skat, table.table_id, [(table.watcher, None)]) as (watcher,):
            offered = agent.read(table.table_id).json()["hand"]["auction"]["values"]
            assert value in offered

            answer = agent.auction_step(AUCTION_BID_TOOL, table, value=value)

            assert not answer.is_error, answer.text
            assert table.record.version == before + 1
            assert table.record.progress.auction == (Bid(MIDDLEHAND, value),)
            words = next(view["hand"]["auction"]["words"] for view in watcher if view["version"] == before + 1)
            seat = seats_from(DEALER_SEAT)[MIDDLEHAND]
            assert [(word["seat"], word["action"], word["value"]) for word in words] == [
                (seat, AuctionAction.BID, value)
            ]
        direct = skat.client.get(f"{TABLES_PATH}/{table.table_id}", headers=table.at[MIDDLEHAND])
        assert agent.read(table.table_id).json() == direct.json()

    def test_a_hold_facing_a_bid_leaves_the_bid_standing_and_gives_the_bidder_the_turn(self, agent, forehand_auction):
        table = forehand_auction
        table.middlehand_bids(VALID_BIDS[0])
        table.skat.client.cookies.clear()

        answer = agent.auction_step(AUCTION_HOLD_TOOL, table)

        assert not answer.is_error, answer.text
        assert table.record.progress.auction == (Bid(MIDDLEHAND, VALID_BIDS[0]), Hold(FOREHAND))
        auction = auction_of(table.record)
        assert (auction.awaiting, auction.actor) == (Awaiting.BID, MIDDLEHAND)

    def test_a_pass_takes_the_agent_out_and_a_later_step_is_refused_as_already_passed(self, agent, middlehand_auction):
        table = middlehand_auction
        assert not agent.auction_step(AUCTION_PASS_TOOL, table).is_error
        assert table.record.progress.auction == (Pass(MIDDLEHAND),)

        again = agent.auction_step(AUCTION_PASS_TOOL, table, command_id="agent-step-0002")

        assert again.is_error
        assert again.json()["reason"] == BidRefusal.ALREADY_PASSED

    def test_the_forehand_plays_after_both_others_passed_and_declares_at_the_lowest_value(
        self, agent, forehand_auction
    ):
        table = forehand_auction
        person_passes(table, MIDDLEHAND)
        person_passes(table, REARHAND)

        answer = agent.auction_step(AUCTION_PLAY_TOOL, table)

        assert not answer.is_error, answer.text
        assert auction_of(table.record).result == Declared(FOREHAND, VALID_BIDS[0])

    def test_the_agents_third_pass_ends_the_hand_passed_in(self, agent, forehand_auction):
        table = forehand_auction
        person_passes(table, MIDDLEHAND)
        person_passes(table, REARHAND)

        answer = agent.auction_step(AUCTION_PASS_TOOL, table)

        assert not answer.is_error, answer.text
        assert answer.json()["hand"] is None
        assert answer.json()["passed_in"] is not None
        assert table.record.hand is None

    def test_the_same_call_again_answers_the_same_and_steps_nothing_twice(self, agent, middlehand_auction):
        table = middlehand_auction
        version = table.record.version
        first = agent.auction_step(AUCTION_BID_TOOL, table, value=VALID_BIDS[0])
        after_first = stored(table.skat)

        again = agent.auction_step(AUCTION_BID_TOOL, table, value=VALID_BIDS[0], version=version)

        assert (again.is_error, again.text) == (first.is_error, first.text)
        assert stored(table.skat) == after_first

    def test_the_same_command_id_with_another_value_is_refused_as_reused(self, agent, middlehand_auction):
        table = middlehand_auction
        agent.auction_step(AUCTION_BID_TOOL, table, value=VALID_BIDS[0])
        before = stored(table.skat)

        answer = agent.auction_step(AUCTION_BID_TOOL, table, value=VALID_BIDS[1])

        assert answer.is_error
        assert "reused" in answer.text
        assert stored(table.skat) == before

    @pytest.mark.parametrize(
        ("tool", "changes", "reason"),
        [
            pytest.param(AUCTION_PASS_TOOL, {"version": 0}, Refusal.STALE_VERSION, id="stale version"),
            pytest.param(AUCTION_BID_TOOL, {"value": 17}, BidRefusal.INVALID_VALUE, id="no valid bid"),
            pytest.param(AUCTION_HOLD_TOOL, {}, BidRefusal.WRONG_ACTION, id="hold while a bid is awaited"),
        ],
    )
    def test_a_refused_step_is_a_failed_result_with_the_routes_reason_and_spends_the_command_id(
        self, skat, agent, middlehand_auction, tool, changes, reason
    ):
        table = middlehand_auction
        before = stored(skat)

        answer = agent.auction_step(tool, table, command_id="agent-step-refused", **changes)

        assert answer.is_error
        assert answer.json()["reason"] == reason
        assert stored(skat)[0] == before[0]
        assert (agent_account_id(skat), "agent-step-refused") in skat.store.receipts

    def test_a_step_out_of_turn_is_refused_as_not_your_turn(self, skat, agent, forehand_auction):
        table = forehand_auction
        before = stored(skat)

        answer = agent.auction_step(AUCTION_PASS_TOOL, table, command_id="agent-step-refused")

        assert answer.is_error
        assert answer.json()["reason"] == BidRefusal.NOT_YOUR_TURN
        assert stored(skat)[0] == before[0]
        assert (agent_account_id(skat), "agent-step-refused") in skat.store.receipts

    def test_a_bid_not_above_the_standing_one_is_refused(self, agent, middlehand_auction):
        table = middlehand_auction
        agent.auction_step(AUCTION_BID_TOOL, table, value=VALID_BIDS[1])
        person_steps(table, FOREHAND, TABLE_AUCTION_HOLD_SUFFIX)
        before = stored(table.skat)

        answer = agent.auction_step(AUCTION_BID_TOOL, table, command_id="agent-step-refused", value=VALID_BIDS[1])

        assert answer.is_error
        assert answer.json()["reason"] == BidRefusal.NOT_ABOVE_STANDING
        assert stored(table.skat)[0] == before[0]
        assert (agent_account_id(table.skat), "agent-step-refused") in table.skat.store.receipts

    def test_an_agent_without_a_chair_is_refused_as_not_seated(self, skat, agent):
        agent.admitted()
        table = Table(skat)
        before = stored(skat)

        answer = agent.auction_step(AUCTION_PASS_TOOL, table, command_id="agent-step-refused")

        assert answer.is_error
        assert answer.json()["reason"] == Refusal.NOT_SEATED
        assert stored(skat)[0] == before[0]
        assert (agent_account_id(skat), "agent-step-refused") in skat.store.receipts

    def test_a_table_with_no_hand_is_refused_as_no_hand(self, skat, agent):
        headers = agent.admitted()
        table_id = skat.create(headers).json()["id"]
        before = stored(skat)

        answer = agent.call(AUCTION_PASS_TOOL, table_id=table_id, command_id="agent-step-0001", version=1)

        assert answer.is_error
        assert answer.json()["reason"] == Refusal.NO_HAND
        assert stored(skat)[0] == before[0]
        assert (agent_account_id(skat), "agent-step-0001") in skat.store.receipts

    @pytest.mark.parametrize(
        ("tool", "arguments"),
        [
            pytest.param(AUCTION_BID_TOOL, {}, id="bid without a value"),
            pytest.param(AUCTION_HOLD_TOOL, {"value": VALID_BIDS[0]}, id="hold with a value"),
            pytest.param(AUCTION_PASS_TOOL, {"action": "pass"}, id="pass names an action"),
        ],
    )
    def test_an_argument_that_breaks_the_tools_shape_stores_nothing(
        self, skat, agent, middlehand_auction, tool, arguments
    ):
        before = stored(skat)

        answer = agent.auction_step(tool, middlehand_auction, **arguments)

        assert answer.is_error
        assert stored(skat) == before

    def test_the_step_is_recorded_under_the_agents_own_account_never_its_owners(self, skat, agent, middlehand_auction):
        agent.auction_step(AUCTION_PASS_TOOL, middlehand_auction)

        accounts = {account_id for account_id, _ in skat.store.receipts}
        assert agent_account_id(skat) in accounts
        assert skat.stores.accounts.get(OWNER) is None


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


class TestFollowingSuit:
    def test_a_followers_illegal_card_is_refused_as_must_follow_as_the_direct_route_refuses_it(self, skat, agent):
        table = AgentTable(skat, agent.admitted(), MIDDLEHAND)
        table.declared_hand_game()
        table.accepted(card("S7"))
        skat.client.cookies.clear()
        before = stored(skat)

        answer = agent.play(table, card("H7"), command_id="agent-move-illegal")

        assert answer.is_error
        assert answer.json()["reason"] == PlayRefusal.MUST_FOLLOW
        assert stored(skat)[0] == before[0]
        direct = table.send(table.at[MIDDLEHAND], card("H7"))
        assert (direct.status_code, direct.json()["reason"]) == (409, answer.json()["reason"])


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
            pytest.param("POST", "/auction", {"action": "pass", "version": 1}, id="the auction path without a step"),
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
