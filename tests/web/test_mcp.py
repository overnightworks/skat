import logline
import pytest
import structlog.testing
from agents.mcp_wire import MCP_ENDPOINT_PATH
from agents.member import ACCEPT_INVITATION_TOOL

from skat.engine.bidding import VALID_BIDS, Awaiting, Bid, BidRefusal, Declared, Hold, Pass
from skat.engine.deal import Position, seats_from
from skat.engine.tricks import CardPlayed, PlayRefusal
from skat.table.auction import AuctionAction
from skat.table.hand_state import auction_of
from skat.table.records import Refusal
from skat.web.auction import TABLE_AUCTION_HOLD_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.declaring import TABLE_DECLARING_TAKE_SUFFIX
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.mcp import (
    AGREE_TO_ABORT_HAND_TOOL,
    AGREE_TO_END_SERIES_TOOL,
    AGREE_TO_GIVE_UP_TOOL,
    AUCTION_BID_TOOL,
    AUCTION_HOLD_TOOL,
    AUCTION_PASS_TOOL,
    AUCTION_PLAY_TOOL,
    CONTINUE_AFTER_RESULT_TOOL,
    DECLARE_GAME_TOOL,
    DECLINE_GIVE_UP_TOOL,
    GIVE_UP_GAME_TOOL,
    NUDGE_SEAT_TOOL,
    OPEN_TABLE_TOOL,
    PLAY_CARD_TOOL,
    PLAY_OPEN_TOOL,
    PUT_BACK_CARDS_TOOL,
    RAMSCH_DECLARE_GRAND_HAND_TOOL,
    RAMSCH_PUSH_SKAT_TOOL,
    RAMSCH_PUT_BACK_CARDS_TOOL,
    RAMSCH_TAKE_SKAT_TOOL,
    READ_PAUSED_TABLES_TOOL,
    READ_RULE_SETS_TOOL,
    READ_SERIES_LIST_TOOL,
    READ_TABLE_TOOL,
    REFUSE_TO_ABORT_HAND_TOOL,
    REFUSE_TO_END_SERIES_TOOL,
    SAVE_RULE_SET_TOOL,
    SAY_KONTRA_TOOL,
    SAY_NO_WORD_TOOL,
    SHORTEN_GAME_TOOL,
    SIT_DOWN_TOOL,
    STAND_UP_TOOL,
    START_NEW_SERIES_TOOL,
    TAKE_SKAT_TOOL,
    THROW_DOWN_CARDS_TOOL,
)
from skat.web.playing import TABLE_GIVE_UP_SUFFIX
from skat.web.tables import (
    TABLES_PATH,
    AwaitingToken,
)
from tests.support.payload_cards import CARDS_BY_SEAT, DEALER_SEAT, SKAT_CARDS, cards_in, wire_cards
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import agent_account_id, person_passes, person_steps
from tests.web.support.playing import Table, card, card_body, cards, ending_of
from tests.web.support.series import play_a_series
from tests.web.support.skat import UNKNOWN_ID, AgentTable, Skat, stored, streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
AUCTION_TOOLS = {AUCTION_BID_TOOL, AUCTION_HOLD_TOOL, AUCTION_PASS_TOOL, AUCTION_PLAY_TOOL}
DECLARING_TOOLS = {TAKE_SKAT_TOOL, PUT_BACK_CARDS_TOOL, DECLARE_GAME_TOOL}
PUSHING_TOOLS = {
    RAMSCH_TAKE_SKAT_TOOL,
    RAMSCH_PUT_BACK_CARDS_TOOL,
    RAMSCH_PUSH_SKAT_TOOL,
    RAMSCH_DECLARE_GRAND_HAND_TOOL,
}
STEP_TOOLS = AUCTION_TOOLS | DECLARING_TOOLS | PUSHING_TOOLS
OWNER = "the-agents-owner"
METADATA_PATH = f"/.well-known/oauth-protected-resource{MCP_ENDPOINT_PATH}"


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


class TestTools:
    def test_the_front_declares_the_table_tools_and_only_the_four_reads_are_read_only(self, agent):
        answer = agent.offered_every_tool().request("tools/list")

        tools = {tool["name"]: tool for tool in answer.json()["result"]["tools"]}
        assert (
            set(tools)
            == {
                ACCEPT_INVITATION_TOOL,
                READ_TABLE_TOOL,
                READ_SERIES_LIST_TOOL,
                READ_PAUSED_TABLES_TOOL,
                PLAY_CARD_TOOL,
                GIVE_UP_GAME_TOOL,
                SHORTEN_GAME_TOOL,
                PLAY_OPEN_TOOL,
                THROW_DOWN_CARDS_TOOL,
                AGREE_TO_GIVE_UP_TOOL,
                DECLINE_GIVE_UP_TOOL,
                CONTINUE_AFTER_RESULT_TOOL,
                AGREE_TO_END_SERIES_TOOL,
                REFUSE_TO_END_SERIES_TOOL,
                AGREE_TO_ABORT_HAND_TOOL,
                REFUSE_TO_ABORT_HAND_TOOL,
                SAY_KONTRA_TOOL,
                SAY_NO_WORD_TOOL,
                OPEN_TABLE_TOOL,
                SIT_DOWN_TOOL,
                STAND_UP_TOOL,
                READ_RULE_SETS_TOOL,
                SAVE_RULE_SET_TOOL,
                START_NEW_SERIES_TOOL,
                NUDGE_SEAT_TOOL,
            }
            | STEP_TOOLS
        )
        reads = {READ_TABLE_TOOL, READ_SERIES_LIST_TOOL, READ_PAUSED_TABLES_TOOL, READ_RULE_SETS_TOOL}
        assert all(tools[name]["annotations"]["readOnlyHint"] is True for name in reads)
        for name in set(tools) - reads:
            assert "readOnlyHint" not in tools[name].get("annotations", {})

    def test_each_step_tool_has_a_description_of_its_own(self, agent):
        answer = agent.offered_every_tool().request("tools/list")

        tools = {tool["name"]: tool for tool in answer.json()["result"]["tools"]}
        assert len({tools[name]["description"] for name in STEP_TOOLS}) == len(STEP_TOOLS)

    @pytest.mark.parametrize(
        ("tool", "token"),
        [
            pytest.param(AUCTION_BID_TOOL, AwaitingToken.BID, id="bid"),
            pytest.param(AUCTION_HOLD_TOOL, AwaitingToken.ANSWER, id="hold"),
            pytest.param(AUCTION_PLAY_TOOL, AwaitingToken.PLAY, id="play"),
        ],
    )
    def test_a_tool_description_names_the_awaiting_value_its_step_fits(self, agent, tool, token):
        answer = agent.offered_every_tool().request("tools/list")

        tools = {listed["name"]: listed for listed in answer.json()["result"]["tools"]}
        assert f'is "{token.value}"' in tools[tool]["description"]

    @pytest.mark.parametrize(
        ("shared_input", "rule_phrase"),
        [("command_id", "command id"), ("table_id", "table id"), ("version", "come from")],
    )
    def test_a_shared_input_is_explained_by_its_field_and_by_no_move_description(
        self, agent, shared_input, rule_phrase
    ):
        answer = agent.offered_every_tool().request("tools/list")

        moves = [tool for tool in answer.json()["result"]["tools"] if "command_id" in tool["inputSchema"]["properties"]]
        having = [tool for tool in moves if shared_input in tool["inputSchema"]["properties"]]
        assert having
        assert all(tool["inputSchema"]["properties"][shared_input].get("description") for tool in having)
        assert not [tool["name"] for tool in moves if rule_phrase in tool["description"]]

    def test_the_resource_metadata_is_public(self, skat):
        answer = skat.client.get(METADATA_PATH)

        assert answer.status_code == 200
        assert answer.json()["resource"] == f"{TEST_PUBLIC_ORIGIN}{MCP_ENDPOINT_PATH}"


class TestRequestLine:
    def test_names_the_account_behind_the_agents_token(self, skat, agent):
        agent.admitted()

        with structlog.testing.capture_logs() as logs:
            agent.request("tools/list")

        (line,) = [log for log in logs if log["event"] == logline.REQUEST_EVENT]
        assert (line["sub"], line["status"]) == (agent_account_id(skat), 200)

    def test_names_the_endpoint_pattern_as_the_route(self, agent):
        agent.admitted()

        with structlog.testing.capture_logs() as logs:
            agent.request("tools/list")

        (line,) = [log for log in logs if log["event"] == logline.REQUEST_EVENT]
        assert line["route"] == MCP_ENDPOINT_PATH


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

    def test_the_options_of_a_table_read_at_the_tool_as_the_route_gives_them(self, skat, agent):
        headers = agent.admitted()
        table_id = skat.create(headers, options={"show_running_points": True}).json()["id"]

        view = agent.read(table_id).json()

        assert view["options"] == {"show_running_points": True, "kontra": None, "bock": None, "ramsch": None}
        assert view == skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers).json()

    def test_the_standings_of_a_played_series_read_at_the_tool_as_the_route_gives_them(self, skat, agent):
        agent.admitted()
        table, names = play_a_series(skat)

        view = agent.read(table.table_id).json()

        standings = view["series"]["standings"]
        assert view["series"]["over"] is True
        assert {each["display_name"] for each in standings} == set(names)
        assert view["series"] == table.read_as(table.watcher).json()["series"]

    def test_the_series_list_reads_at_the_tool_as_the_route_gives_it(self, skat, agent):
        agent.admitted()
        table, _ = play_a_series(skat)

        listed = agent.call(READ_SERIES_LIST_TOOL, table_id=table.table_id)

        route = skat.client.get(f"{TABLES_PATH}/{table.table_id}{TABLE_LIST_SUFFIX}", headers=table.watcher)
        assert not listed.is_error, listed.text
        assert listed.json() == route.json()
        assert len(listed.json()["entries"]) == 3
        assert agent.call(READ_SERIES_LIST_TOOL, table_id=UNKNOWN_ID).is_error

    def test_an_agent_without_a_chair_gets_the_watchers_view_without_any_card(self, skat, agent):
        agent.admitted()
        table = Table(skat)
        table.declared_hand_game()

        view = agent.read(table.table_id).json()

        assert cards_in(view) == set()
        assert not any(chair["is_mine"] for chair in view["chairs"])

    def test_the_declarer_sees_the_skat_it_took_as_its_own_view_shows_it(self, skat, agent):
        table = AgentTable(skat, agent, MIDDLEHAND)
        table.middlehand_wins()
        skat.client.post(
            f"{TABLES_PATH}/{table.table_id}{TABLE_DECLARING_TAKE_SUFFIX}",
            json={"command_id": "command-take", "version": table.record.version},
            headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[MIDDLEHAND]},
        )

        view = agent.read(table.table_id).json()

        assert wire_cards(SKAT_CARDS) <= cards_in(view)
        direct = skat.client.get(f"{TABLES_PATH}/{table.table_id}", headers=table.at[MIDDLEHAND])
        assert view == direct.json()

    def test_a_hand_declarer_never_sees_the_skat(self, skat, agent):
        table = AgentTable(skat, agent, MIDDLEHAND)
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


class TestCommandAnswers:
    def test_a_played_card_is_answered_with_what_was_done_and_no_table(self, agent, forehand_table):
        before = forehand_table.record.version

        answer = agent.play(forehand_table, card("S7"))

        assert answer.json() == {"done": PLAY_CARD_TOOL, "table_id": forehand_table.table_id, "version": before + 1}

    @pytest.mark.parametrize(
        ("tool", "changes"),
        [
            pytest.param(AUCTION_BID_TOOL, {"value": VALID_BIDS[0]}, id="bid"),
            pytest.param(AUCTION_PASS_TOOL, {}, id="pass"),
        ],
    )
    def test_an_auction_step_is_answered_with_what_was_done_and_no_table(
        self, agent, middlehand_auction, tool, changes
    ):
        table = middlehand_auction
        before = table.record.version

        answer = agent.take_step(tool, table, **changes)

        assert answer.json() == {"done": tool, "table_id": table.table_id, "version": before + 1}

    def test_the_version_an_answer_names_is_the_one_the_next_command_takes(self, agent, forehand_table):
        first = agent.play(forehand_table, card("S7")).json()
        forehand_table.skat.client.cookies.clear()

        after = agent.read(forehand_table.table_id).json()

        assert (after["id"], after["version"]) == (first["table_id"], first["version"])

    def test_a_persons_route_for_the_same_command_still_answers_with_the_table(self, middlehand_auction):
        table = middlehand_auction
        page_answer = table.skat.client.post(
            f"{TABLES_PATH}/{table.table_id}{TABLE_AUCTION_PASS_SUFFIX}",
            json={"command_id": table.fresh_id(), "version": table.record.version},
            headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[MIDDLEHAND]},
        )

        assert page_answer.status_code == 200, page_answer.text
        assert {"id", "version", "chairs", "hand"} <= set(page_answer.json())


class TestGiveUpGame:
    def give_up(self, agent, table, *, command_id="agent-give-up-0001", **changes):
        return agent.call(
            GIVE_UP_GAME_TOOL,
            table_id=table.table_id,
            command_id=command_id,
            **{"version": table.record.version, **changes},
        )

    def test_an_agent_declarer_loses_the_game_at_once_under_its_own_account(self, skat, agent):
        table = AgentTable(skat, agent, MIDDLEHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()

        answer = self.give_up(agent, table)

        assert not answer.is_error, answer.text
        result = agent.read(table.table_id).json()["result"]
        assert result["won"] is False
        assert (result["multiplier"], result["list_bonus"], result["announcement_missed"]) == (3, -50, False)
        assert ending_of(result) == ("given-up", 1)
        assert table.read_as(table.at[MIDDLEHAND]).json()["result"] == result
        assert table.record.hand is None
        assert len(table.record.game_list) == 1

    def test_an_agent_declarer_with_eight_cards_asks_through_the_give_up_tool(self, skat, agent):
        table = AgentTable(skat, agent, MIDDLEHAND)
        table.declared_hand_game()
        table.played_out(cards("S7 S9 D7 H7"))
        skat.client.cookies.clear()

        answer = self.give_up(agent, table)

        assert not answer.is_error, answer.text
        assert agent.read(table.table_id).json()["hand"]["playing"]["give_up"] == {
            "asking_seat": 1,
            "declined_seat": None,
        }

    def test_a_refused_give_up_is_a_failed_result_with_the_reason_and_spends_the_id(self, agent, forehand_table):
        before = stored(forehand_table.skat)

        answer = self.give_up(agent, forehand_table, version=0)

        assert answer.is_error
        assert answer.json()["reason"] == Refusal.STALE_VERSION
        assert stored(forehand_table.skat)[0] == before[0]
        assert "reused" in self.give_up(agent, forehand_table).text


class TestAnsweringAGiveUp:
    """The declarer is a person asking with eight cards; the agent holds an opponent's chair."""

    def answer(self, agent, table, tool, *, command_id="agent-answer-0001", **changes):
        return agent.call(
            tool,
            table_id=table.table_id,
            command_id=command_id,
            **{"version": table.record.version, **changes},
        )

    @pytest.fixture
    def asked(self, skat, agent):
        table = AgentTable(skat, agent, FOREHAND)
        table.declared_hand_game()
        table.played_out(cards("S7 S9 D7"))
        table.accepted(card("H7"))
        assert table.act(TABLE_GIVE_UP_SUFFIX).status_code == 200
        skat.client.cookies.clear()
        return table

    def test_the_agent_opponent_sees_the_request_and_its_yes_ends_the_game_lost_for_the_declarer(self, agent, asked):
        assert agent.read(asked.table_id).json()["hand"]["playing"]["give_up"] == {
            "asking_seat": 1,
            "declined_seat": None,
        }

        answer = self.answer(agent, asked, AGREE_TO_GIVE_UP_TOOL)

        assert not answer.is_error, answer.text
        result = agent.read(asked.table_id).json()["result"]
        assert (result["won"], result["list_bonus"]) == (False, -50)
        assert ending_of(result) == ("given-up", 1)
        assert asked.record.hand is None
        assert len(asked.record.game_list) == 1

    def test_the_agent_opponents_no_is_named_in_the_request_and_the_game_goes_on(self, agent, asked):
        answer = self.answer(agent, asked, DECLINE_GIVE_UP_TOOL)

        assert not answer.is_error, answer.text
        assert agent.read(asked.table_id).json()["hand"]["playing"]["give_up"] == {"asking_seat": 1, "declined_seat": 3}
        assert asked.record.hand is not None

    @pytest.mark.parametrize("tool", [AGREE_TO_GIVE_UP_TOOL, DECLINE_GIVE_UP_TOOL])
    def test_a_refused_answer_is_a_failed_result_with_the_reason_and_spends_the_id(self, agent, asked, tool):
        before = stored(asked.skat)

        answer = self.answer(agent, asked, tool, version=0)

        assert answer.is_error
        assert answer.json()["reason"] == Refusal.STALE_VERSION
        assert stored(asked.skat)[0] == before[0]
        assert "reused" in self.answer(agent, asked, tool).text


class TestThrowDownCards:
    def throw_down(self, agent, table, *, command_id="agent-throw-down-0001", **changes):
        return agent.call(
            THROW_DOWN_CARDS_TOOL,
            table_id=table.table_id,
            command_id=command_id,
            **{"version": table.record.version, **changes},
        )

    @pytest.mark.parametrize(
        ("position", "won"),
        [pytest.param(MIDDLEHAND, False, id="declarer"), pytest.param(FOREHAND, True, id="opponent")],
    )
    def test_an_agent_ends_the_game_for_its_side_under_its_own_account(self, skat, agent, position, won):
        table = AgentTable(skat, agent, position)
        table.declared_hand_game()
        skat.client.cookies.clear()

        answer = self.throw_down(agent, table)

        assert not answer.is_error, answer.text
        result = agent.read(table.table_id).json()["result"]
        assert result["won"] is won
        assert (result["multiplier"], result["list_bonus"], result["announcement_missed"]) == (
            5,
            50 if won else -50,
            False,
        )
        assert ending_of(result) == ("thrown-down", 1 if position is MIDDLEHAND else 3)
        assert table.record.hand is None
        assert len(table.record.game_list) == 1

    def test_a_refused_throw_down_is_a_failed_result_with_the_reason_and_spends_the_id(self, agent, forehand_table):
        before = stored(forehand_table.skat)

        answer = self.throw_down(agent, forehand_table, version=0)

        assert answer.is_error
        assert answer.json()["reason"] == Refusal.STALE_VERSION
        assert stored(forehand_table.skat)[0] == before[0]
        assert "reused" in self.throw_down(agent, forehand_table).text


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

            answer = agent.take_step(AUCTION_BID_TOOL, table, value=value)

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

        answer = agent.take_step(AUCTION_HOLD_TOOL, table)

        assert not answer.is_error, answer.text
        assert table.record.progress.auction == (Bid(MIDDLEHAND, VALID_BIDS[0]), Hold(FOREHAND))
        auction = auction_of(table.record)
        assert (auction.awaiting, auction.actor) == (Awaiting.BID, MIDDLEHAND)

    def test_a_pass_takes_the_agent_out_and_a_later_step_is_refused_as_already_passed(self, agent, middlehand_auction):
        table = middlehand_auction
        assert not agent.take_step(AUCTION_PASS_TOOL, table).is_error
        assert table.record.progress.auction == (Pass(MIDDLEHAND),)

        again = agent.take_step(AUCTION_PASS_TOOL, table, command_id="agent-step-0002")

        assert again.is_error
        assert again.json()["reason"] == BidRefusal.ALREADY_PASSED

    def test_the_forehand_plays_after_both_others_passed_and_declares_at_the_lowest_value(
        self, agent, forehand_auction
    ):
        table = forehand_auction
        person_passes(table, MIDDLEHAND)
        person_passes(table, REARHAND)

        answer = agent.take_step(AUCTION_PLAY_TOOL, table)

        assert not answer.is_error, answer.text
        assert auction_of(table.record).result == Declared(FOREHAND, VALID_BIDS[0])

    def test_the_agents_third_pass_ends_the_hand_passed_in(self, agent, forehand_auction):
        table = forehand_auction
        person_passes(table, MIDDLEHAND)
        person_passes(table, REARHAND)

        answer = agent.take_step(AUCTION_PASS_TOOL, table)

        assert not answer.is_error, answer.text
        assert agent.read(table.table_id).json()["passed_in"] is not None
        assert table.record.hand is None

    def test_the_same_call_again_answers_the_same_and_steps_nothing_twice(self, agent, middlehand_auction):
        table = middlehand_auction
        version = table.record.version
        first = agent.take_step(AUCTION_BID_TOOL, table, value=VALID_BIDS[0])
        after_first = stored(table.skat)

        again = agent.take_step(AUCTION_BID_TOOL, table, value=VALID_BIDS[0], version=version)

        assert (again.is_error, again.text) == (first.is_error, first.text)
        assert stored(table.skat) == after_first

    def test_the_same_command_id_with_another_value_is_refused_as_reused(self, agent, middlehand_auction):
        table = middlehand_auction
        agent.take_step(AUCTION_BID_TOOL, table, value=VALID_BIDS[0])
        before = stored(table.skat)

        answer = agent.take_step(AUCTION_BID_TOOL, table, value=VALID_BIDS[1])

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

        answer = agent.take_step(tool, table, command_id="agent-step-refused", **changes)

        assert answer.is_error
        assert answer.json()["reason"] == reason
        assert stored(skat)[0] == before[0]
        assert (agent_account_id(skat), "agent-step-refused") in skat.store.receipts

    def test_a_step_out_of_turn_is_refused_as_not_your_turn(self, skat, agent, forehand_auction):
        table = forehand_auction
        before = stored(skat)

        answer = agent.take_step(AUCTION_PASS_TOOL, table, command_id="agent-step-refused")

        assert answer.is_error
        assert answer.json()["reason"] == BidRefusal.NOT_YOUR_TURN
        assert stored(skat)[0] == before[0]
        assert (agent_account_id(skat), "agent-step-refused") in skat.store.receipts

    def test_a_bid_not_above_the_standing_one_is_refused(self, agent, middlehand_auction):
        table = middlehand_auction
        agent.take_step(AUCTION_BID_TOOL, table, value=VALID_BIDS[1])
        person_steps(table, FOREHAND, TABLE_AUCTION_HOLD_SUFFIX)
        before = stored(table.skat)

        answer = agent.take_step(AUCTION_BID_TOOL, table, command_id="agent-step-refused", value=VALID_BIDS[1])

        assert answer.is_error
        assert answer.json()["reason"] == BidRefusal.NOT_ABOVE_STANDING
        assert stored(table.skat)[0] == before[0]
        assert (agent_account_id(table.skat), "agent-step-refused") in table.skat.store.receipts

    def test_an_agent_without_a_chair_is_refused_as_not_seated(self, skat, agent):
        agent.admitted()
        table = Table(skat)
        before = stored(skat)

        answer = agent.offered_every_tool().take_step(AUCTION_PASS_TOOL, table, command_id="agent-step-refused")

        assert answer.is_error
        assert answer.json()["reason"] == Refusal.NOT_SEATED
        assert stored(skat)[0] == before[0]
        assert (agent_account_id(skat), "agent-step-refused") in skat.store.receipts

    def test_a_table_with_no_hand_is_refused_as_no_hand(self, skat, agent):
        headers = agent.admitted()
        table_id = skat.create(headers).json()["id"]
        before = stored(skat)

        answer = agent.offered_every_tool().call(
            AUCTION_PASS_TOOL, table_id=table_id, command_id="agent-step-0001", version=1
        )

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

        answer = agent.take_step(tool, middlehand_auction, **arguments)

        assert answer.is_error
        assert stored(skat) == before

    def test_the_step_is_recorded_under_the_agents_own_account_never_its_owners(self, skat, agent, middlehand_auction):
        agent.take_step(AUCTION_PASS_TOOL, middlehand_auction)

        accounts = {account_id for account_id, _ in skat.store.receipts}
        assert agent_account_id(skat) in accounts
        assert skat.stores.accounts.get(OWNER) is None


class TestFollowingSuit:
    def test_a_followers_illegal_card_is_refused_as_must_follow_as_the_direct_route_refuses_it(self, skat, agent):
        table = AgentTable(skat, agent, MIDDLEHAND)
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
