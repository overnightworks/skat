"""An agent is offered the tools of its table's moment and no others, and is told when the moment changes; a person's
token is offered every tool.
"""

from contextlib import nullcontext
from dataclasses import replace

import pytest
from agents.member import ACCEPT_INVITATION_TOOL, STANDING_URI
from starlette.concurrency import run_in_threadpool

from skat.table.records import Series, TableId
from skat.web.declaring import TABLE_DECLARING_TAKE_SUFFIX
from skat.web.mcp import (
    AUCTION_BID_TOOL,
    AUCTION_HOLD_TOOL,
    AUCTION_PASS_TOOL,
    AUCTION_PLAY_TOOL,
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
    THROW_REACTION_TOOL,
    TOOLS_OF_MOMENT,
)
from skat.web.member_place import ACCEPT_INVITATION_DECLARATION, SET_TURN_STATE_DECLARATION
from tests.support.calls import call_facts
from tests.support.played_game import a_whole_game
from tests.web.support.agent import Agent, agent_account_id, person_passes, person_steps, view_uri_of, window_uri_of
from tests.web.support.calling import a_person
from tests.web.support.playing import FOREHAND, MIDDLEHAND, REARHAND
from tests.web.support.sdk_agent import TOOLS_CHANGED, SdkAgent
from tests.web.support.series import headers_of, tap_weiter
from tests.web.support.skat import AgentTable, running_skat, streams_of

READS = {READ_TABLE_TOOL, READ_SERIES_LIST_TOOL, READ_PAUSED_TABLES_TOOL, READ_RULE_SETS_TOOL}
SEATED = READS | {
    STAND_UP_TOOL,
    NUDGE_SEAT_TOOL,
    THROW_REACTION_TOOL,
    ACCEPT_INVITATION_DECLARATION.name,
    SET_TURN_STATE_DECLARATION.name,
}
NOT_OFFERED = "the tool is not offered now"


skat = pytest.fixture(name="skat")(running_skat)


class TestTheListFollowsTheMoment:
    def test_an_agent_at_no_table_is_offered_the_lobby_tools(self, agent):
        agent.admitted()

        assert set(agent.listed_tools()) == READS | {
            OPEN_TABLE_TOOL,
            SIT_DOWN_TOOL,
            SAVE_RULE_SET_TOOL,
            ACCEPT_INVITATION_DECLARATION.name,
            SET_TURN_STATE_DECLARATION.name,
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
            ending = [events.next_kind() for _ in range(3)]
            person_steps(table, MIDDLEHAND, TABLE_DECLARING_TAKE_SUFFIX)
            after = [events.next_kind() for _ in range(2)]

        assert (first, second, ending, after) == (
            [window, view],
            [window, view],
            [TOOLS_CHANGED, window, view],
            [window, view],
        )

    def test_the_notice_comes_before_the_standing_when_the_agent_sits_down_and_when_it_stands_up(self, sdk, agent):
        with sdk.connected() as session, session.listening(tools_list_changed=True) as events:
            table_id = agent.open_table().json()["id"]
            sitting = [events.next_kind() for _ in range(2)]
            agent.stand_up(table_id)
            leaving = [events.next_kind() for _ in range(2)]

        assert (sitting, leaving) == ([TOOLS_CHANGED, STANDING_URI], [TOOLS_CHANGED, STANDING_URI])


def on_the_apps_worker(skat, step, *arguments):
    """Runs a server step of the service the app wired on a worker of its loop, where the pulses it tells are heard."""

    async def run():
        return await run_in_threadpool(step, *arguments)

    return skat.client.portal.call(run)


def _a_move(skat, agent):
    table = AgentTable(skat, agent, FOREHAND)
    table.middlehand_bids()
    agent.take_step(AUCTION_PASS_TOOL, table, command_id="agent-pass")
    return lambda _session: person_passes(table, REARHAND)


def _a_sit_that_deals(skat, agent):
    table_id = agent.open_table().json()["id"]
    first, second = skat.member()[0], skat.member()[0]
    skat.sit(first, table_id, 2, command_id="command-sit-2")
    return lambda _session: skat.sit(second, table_id, 3, command_id="command-sit-3")


def _the_deal_after_the_third_continue(skat, agent):
    table = AgentTable(skat, agent, FOREHAND)
    skat.store.tables[table.table_id] = replace(table.record, series=Series(3, 1))
    table.declared_hand_game()
    table.played_out(each.card for each in a_whole_game(table.record))
    for number, headers in enumerate(headers_of(table), start=1):
        assert tap_weiter(skat, headers, table.table_id, f"weiter-{number}").status_code == 200
    everyone = frozenset(chair.occupant.account_id for chair in table.record.chairs)
    return lambda _session: on_the_apps_worker(
        skat, skat.tables.deal_next, TableId(table.table_id), nullcontext(everyone)
    )


def _a_freed_chair(skat, agent):
    agent.admitted()
    table_id = skat.create(skat.member()[0]).json()["id"]
    agent.sit_down(table_id, 2)
    skat.store.hold_due(table_id, agent_account_id(skat))
    return lambda _session: on_the_apps_worker(
        skat, skat.tables.free_held_chair, TableId(table_id), agent_account_id(skat), nullcontext(True)
    )


class TestTheNoticeComesBeforeTheTellingsOfTheSameChange:
    @pytest.mark.parametrize(
        "arrange", [_a_move, _a_sit_that_deals, _the_deal_after_the_third_continue, _a_freed_chair]
    )
    def test_the_stream_writes_the_notice_before_the_window_and_the_view_of_the_change(self, skat, sdk, agent, arrange):
        act = arrange(skat, agent)

        with sdk.connected() as session, session.listening(tools_list_changed=True) as events:
            act(session)
            told = [events.next_kind() for _ in range(2)]

        assert (told[0], told[1] != TOOLS_CHANGED) == (TOOLS_CHANGED, True)

    def test_the_stream_writes_the_notice_of_an_accepted_invitation_before_the_window_and_the_view(self, skat, issuer):
        owner = skat.member()
        agent = Agent(skat, issuer, agent_owner=owner[1].id)
        sdk = SdkAgent(skat, issuer, agent_owner=owner[1].id)
        agent.admitted()
        table_id = skat.create(owner[0]).json()["id"]
        skat.client.cookies.clear()
        offer = on_the_apps_worker(
            skat,
            skat.tables.invite_agent,
            TableId(table_id),
            call_facts(agent.subject, owner[1].id, owner[1].id),
        )

        with (
            streams_of(skat, table_id, [(owner[0], None)]),
            sdk.connected() as session,
            session.listening(tools_list_changed=True) as events,
        ):
            answer = session.call(
                ACCEPT_INVITATION_TOOL, place={"kind": "table", "id": table_id}, invitation=offer.id, epoch=offer.epoch
            )
            told = [events.next_kind() for _ in range(2)]

        assert (answer.is_error, told[0], told[1] != TOOLS_CHANGED) == (False, TOOLS_CHANGED, True)
