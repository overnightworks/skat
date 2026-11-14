"""An agent is offered the tools of its table's moment and no others, and is told when the moment changes; a person's
token is offered every tool.
"""

import pytest

from skat.web.declaring import TABLE_DECLARING_TAKE_SUFFIX
from skat.web.mcp import (
    AUCTION_BID_TOOL,
    AUCTION_HOLD_TOOL,
    AUCTION_PASS_TOOL,
    AUCTION_PLAY_TOOL,
    MCP_GROUP,
    NUDGE_SEAT_TOOL,
    OPEN_TABLE_TOOL,
    PLAY_CARD_TOOL,
    READ_PAUSED_TABLES_TOOL,
    READ_RULE_SETS_TOOL,
    READ_SERIES_LIST_TOOL,
    READ_TABLE_TOOL,
    SAVE_RULE_SET_TOOL,
    SIT_DOWN_TOOL,
    STAND_UP_TOOL,
    TAKE_SKAT_TOOL,
    TOOLS_OF_MOMENT,
)
from skat.web.member_place import ACCEPT_INVITATION_DECLARATION
from tests.web.support.agent import Agent, person_passes, person_steps, view_uri_of, window_uri_of
from tests.web.support.playing import MIDDLEHAND, REARHAND
from tests.web.support.sdk_agent import TOOLS_CHANGED, SdkAgent
from tests.web.support.skat import Skat

READS = {READ_TABLE_TOOL, READ_SERIES_LIST_TOOL, READ_PAUSED_TABLES_TOOL, READ_RULE_SETS_TOOL}
SEATED = READS | {STAND_UP_TOOL, NUDGE_SEAT_TOOL, ACCEPT_INVITATION_DECLARATION.name}
NOT_OFFERED = "the tool is not offered now"


@pytest.fixture
def skat(hold, issuer, time):
    skat = Skat(
        lambda: hold, issuer_transports=issuer.transports, chair_clock=time.clock, chair_scheduler=time, now=time.moment
    )
    with skat.client:
        yield skat


@pytest.fixture
def sdk(skat, issuer):
    return SdkAgent(skat, issuer)


def a_person(skat, issuer):
    return Agent(skat, issuer, skat.member()[1].id, agent_owner=None, agent_name=None, groups=[MCP_GROUP])


def events_until_the_notice(events, within=4):
    """The events up to and including the notice that the tool list changed; the notice is not among them if none of
    the first `within` events is it.
    """
    seen = []
    while len(seen) < within and TOOLS_CHANGED not in seen:
        seen.append(events.next_kind())
    return seen


class TestTheListFollowsTheMoment:
    def test_an_agent_at_no_table_is_offered_the_lobby_tools(self, agent):
        agent.admitted()

        assert set(agent.listed_tools()) == READS | {
            OPEN_TABLE_TOOL,
            SIT_DOWN_TOOL,
            SAVE_RULE_SET_TOOL,
            ACCEPT_INVITATION_DECLARATION.name,
        }

    def test_a_seated_agent_in_the_auction_is_offered_the_four_auction_tools_and_the_seated_ones(
        self, agent, middlehand_auction
    ):
        assert set(agent.listed_tools()) == SEATED | {
            AUCTION_BID_TOOL,
            AUCTION_HOLD_TOOL,
            AUCTION_PASS_TOOL,
            AUCTION_PLAY_TOOL,
        }

    def test_the_declarer_is_offered_the_tools_of_declaring_and_nothing_of_the_auction(self, agent, middlehand_auction):
        middlehand_auction.middlehand_wins()

        offered = set(agent.listed_tools())

        assert (TAKE_SKAT_TOOL in offered, AUCTION_BID_TOOL in offered) == (True, False)

    def test_a_player_is_offered_the_tools_of_play_and_none_of_the_auction(self, agent, forehand_table):
        offered = set(agent.listed_tools())

        assert (PLAY_CARD_TOOL in offered, AUCTION_BID_TOOL in offered) == (True, False)

    def test_a_person_is_offered_every_tool_and_so_a_tool_of_every_moment(
        self, skat, issuer, agent, middlehand_auction
    ):
        offered = set(a_person(skat, issuer).listed_tools())

        assert offered > set(agent.listed_tools())
        assert {OPEN_TABLE_TOOL, TAKE_SKAT_TOOL, PLAY_CARD_TOOL} <= offered

    def test_the_moments_together_offer_every_tool_the_front_declares_and_no_other(self, skat, issuer):
        declared = set(a_person(skat, issuer).listed_tools())

        assert set().union(*TOOLS_OF_MOMENT.values()) == declared

    def test_a_tool_not_offered_now_answers_a_failure_and_runs_nothing(self, agent, middlehand_auction):
        answer = agent.take_step(PLAY_CARD_TOOL, middlehand_auction)

        assert (answer.is_error, answer.text) == (True, NOT_OFFERED)


class TestTheAgentIsToldWhenTheListChanges:
    def test_the_notice_comes_when_the_auction_ends_and_not_on_a_move_that_keeps_the_moment(
        self, skat, sdk, agent, forehand_auction
    ):
        table = forehand_auction
        window, view = window_uri_of(table.table_id), view_uri_of(table.table_id)

        with sdk.connected() as session, session.listening(tools_list_changed=True) as events:
            table.middlehand_bids()
            first = [events.next_kind() for _ in range(2)]
            session.call(
                AUCTION_PASS_TOOL, table_id=table.table_id, command_id="agent-pass", version=table.record.version
            )
            second = [events.next_kind() for _ in range(2)]
            person_passes(table, REARHAND)
            ending = sorted(events.next_kind() for _ in range(3))
            person_steps(table, MIDDLEHAND, TABLE_DECLARING_TAKE_SUFFIX)
            after = [events.next_kind() for _ in range(2)]

        assert (first, second, ending, after) == (
            [window, view],
            [window, view],
            sorted([window, view, TOOLS_CHANGED]),
            [window, view],
        )

    def test_the_notice_comes_when_the_agent_sits_down_and_when_it_stands_up(self, sdk, agent):
        with sdk.connected() as session, session.listening(tools_list_changed=True) as events:
            table_id = agent.open_table().json()["id"]
            sitting = events_until_the_notice(events)
            agent.stand_up(table_id)
            leaving = events_until_the_notice(events)

        assert (sitting[-1], leaving[-1]) == (TOOLS_CHANGED, TOOLS_CHANGED)
