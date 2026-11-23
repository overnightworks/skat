"""An agent is offered one fixed list whatever its table is doing, and is told when it sits down or leaves; a person's
token is offered every tool.
"""

from contextlib import nullcontext
from datetime import timedelta

import pytest
from agents.member import ACCEPT_INVITATION_TOOL, STANDING_URI
from starlette.concurrency import run_in_threadpool

from skat.table.records import TableId
from skat.web.declaring import TABLE_DECLARING_TAKE_SUFFIX
from skat.web.mcp import (
    AGREE_TO_ABORT_HAND_TOOL,
    AGREE_TO_END_SERIES_TOOL,
    AUCTION_BID_TOOL,
    AUCTION_HOLD_TOOL,
    AUCTION_PASS_TOOL,
    AUCTION_PLAY_TOOL,
    CHANGE_NEXT_SERIES_SETTINGS_TOOL,
    CONTINUE_AFTER_RESULT_TOOL,
    DECLARE_GAME_TOOL,
    NUDGE_SEAT_TOOL,
    OPEN_TABLE_TOOL,
    PLAY_CARD_TOOL,
    PUT_BACK_CARDS_TOOL,
    RAMSCH_PUT_BACK_CARDS_TOOL,
    READ_PAUSED_TABLES_TOOL,
    READ_RULE_SETS_TOOL,
    READ_SERIES_LIST_TOOL,
    READ_TABLE_TOOL,
    REFUSE_TO_ABORT_HAND_TOOL,
    REFUSE_TO_END_SERIES_TOOL,
    SAVE_RULE_SET_TOOL,
    SAY_KONTRA_TOOL,
    SIT_DOWN_TOOL,
    STAND_UP_TOOL,
    START_NEW_SERIES_TOOL,
    STOP_PLAYING_TOOL,
    TABLE_COMMAND_TOOLS,
    TAKE_SKAT_TOOL,
    THROW_REACTION_TOOL,
)
from skat.web.member_place import ACCEPT_INVITATION_DECLARATION, SET_TURN_STATE_DECLARATION
from tests.support.calls import call_facts
from tests.web.support.agent import Agent, agent_account_id, person_passes, person_steps, view_uri_of, window_uri_of
from tests.web.support.calling import a_person
from tests.web.support.playing import MIDDLEHAND, REARHAND, card, card_body
from tests.web.support.sdk_agent import TOOLS_CHANGED, SdkAgent
from tests.web.support.skat import running_skat, stored, streams_of

READS = {READ_TABLE_TOOL, READ_SERIES_LIST_TOOL, READ_PAUSED_TABLES_TOOL, READ_RULE_SETS_TOOL}
SEATED = READS | {
    STAND_UP_TOOL,
    NUDGE_SEAT_TOOL,
    THROW_REACTION_TOOL,
    ACCEPT_INVITATION_DECLARATION.name,
    SET_TURN_STATE_DECLARATION.name,
}
MOVE_TOOLS = TABLE_COMMAND_TOOLS - {NUDGE_SEAT_TOOL}
NOT_OFFERED = "the tool is not offered now"


skat = pytest.fixture(name="skat")(running_skat)


class TestTheListStaysTheSameThroughAGame:
    def test_an_agent_at_no_table_is_offered_the_lobby_tools(self, agent):
        agent.admitted()

        assert set(agent.listed_tools()) == READS | {
            OPEN_TABLE_TOOL,
            SIT_DOWN_TOOL,
            SAVE_RULE_SET_TOOL,
            ACCEPT_INVITATION_DECLARATION.name,
            SET_TURN_STATE_DECLARATION.name,
        }

    def test_a_seated_agent_is_offered_the_seated_tools_and_the_moves_of_every_moment(self, agent, middlehand_auction):
        assert set(agent.listed_tools()) == SEATED | MOVE_TOOLS

    def test_the_list_after_the_auction_is_the_list_in_it(self, agent, middlehand_auction):
        in_the_auction = agent.listed_tools()
        middlehand_auction.middlehand_wins()

        assert agent.listed_tools() == in_the_auction

    def test_a_person_is_offered_every_tool_and_so_a_tool_of_every_moment(
        self, skat, issuer, agent, middlehand_auction
    ):
        offered = set(a_person(skat, issuer).listed_tools())

        assert offered > set(agent.listed_tools())
        assert {OPEN_TABLE_TOOL, TAKE_SKAT_TOOL, PLAY_CARD_TOOL} <= offered

    def test_the_lobby_and_the_seated_lists_together_offer_every_tool_the_front_declares_and_no_other(
        self, skat, issuer, agent
    ):
        agent.admitted()
        in_the_lobby = set(agent.listed_tools())
        agent.open_table()

        assert in_the_lobby | set(agent.listed_tools()) == set(a_person(skat, issuer).listed_tools())

    def test_a_tool_not_offered_to_an_agent_without_a_chair_answers_a_failure_and_runs_nothing(self, agent):
        agent.admitted()

        answer = agent.call(PLAY_CARD_TOOL, table_id="any", command_id="agent-step-0001", version=0)

        assert (answer.is_error, answer.text) == (True, NOT_OFFERED)


AUCTION_TOOLS = {AUCTION_BID_TOOL, AUCTION_HOLD_TOOL, AUCTION_PASS_TOOL, AUCTION_PLAY_TOOL}

# What each move names besides the table and its retry key. The series moves and the abort votes name no version.
_TWO_CARDS = [card_body(card("S7")), card_body(card("S8"))]
_THE_SERIES = {"series": 1}
MOVE_ARGUMENTS = {
    AUCTION_BID_TOOL: {"value": 18},
    PLAY_CARD_TOOL: card_body(card("S7")),
    PUT_BACK_CARDS_TOOL: {"cards": _TWO_CARDS},
    RAMSCH_PUT_BACK_CARDS_TOOL: {"cards": _TWO_CARDS},
    DECLARE_GAME_TOOL: {"game": "herz", "hand": False, "ouvert": False, "announcement": "none"},
    SAY_KONTRA_TOOL: {"word": "kontra"},
    CONTINUE_AFTER_RESULT_TOOL: {**_THE_SERIES, "ordinal": 1},
    START_NEW_SERIES_TOOL: _THE_SERIES,
    CHANGE_NEXT_SERIES_SETTINGS_TOOL: {**_THE_SERIES, "series_length": 36},
}
UNVERSIONED_MOVES = {
    CONTINUE_AFTER_RESULT_TOOL,
    START_NEW_SERIES_TOOL,
    CHANGE_NEXT_SERIES_SETTINGS_TOOL,
    STOP_PLAYING_TOOL,
    AGREE_TO_END_SERIES_TOOL,
    REFUSE_TO_END_SERIES_TOOL,
    AGREE_TO_ABORT_HAND_TOOL,
    REFUSE_TO_ABORT_HAND_TOOL,
}


def attempt(agent, table, tool):
    """The agent calls the move with the arguments its route takes."""
    version = {} if tool in UNVERSIONED_MOVES else {"version": table.record.version}
    return agent.call(
        tool, table_id=table.table_id, command_id="agent-step-refused", **version, **MOVE_ARGUMENTS.get(tool, {})
    )


class TestAToolOutsideTheMomentIsRefusedByItsRoute:
    @pytest.mark.parametrize("tool", sorted(MOVE_TOOLS - AUCTION_TOOLS))
    def test_a_move_of_another_moment_is_refused_in_the_auction_and_changes_nothing(
        self, skat, agent, middlehand_auction, tool
    ):
        table = middlehand_auction
        before = stored(skat)

        answer = attempt(agent, table, tool)

        assert answer.is_error
        assert answer.json().get("reason"), answer.text
        assert stored(skat)[0] == before[0]

    @pytest.mark.parametrize("tool", sorted(AUCTION_TOOLS))
    def test_an_auction_step_is_refused_in_the_play_and_changes_nothing(self, skat, agent, forehand_table, tool):
        before = stored(skat)

        answer = attempt(agent, forehand_table, tool)

        assert answer.is_error
        assert answer.json().get("reason"), answer.text
        assert stored(skat)[0] == before[0]


class TestTheAgentIsToldWhenTheListChanges:
    def test_no_notice_comes_when_a_moment_ends_and_the_next_begins(self, skat, sdk, agent, forehand_auction):
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
            ending = [events.next_kind() for _ in range(2)]
            person_steps(table, MIDDLEHAND, TABLE_DECLARING_TAKE_SUFFIX)
            after = [events.next_kind() for _ in range(2)]

        assert (first, second, ending, after) == (
            [window, view],
            [window, view],
            [window, view],
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


class TestTheNoticeComesBeforeTheTellingsOfTheSameChange:
    def test_the_stream_writes_the_notice_of_a_freed_chair_before_the_window_and_the_view_of_the_change(
        self, skat, sdk, agent
    ):
        agent.admitted()
        table_id = skat.create(skat.member()[0]).json()["id"]
        agent.sit_down(table_id, 2)
        skat.store.hold_due(table_id, agent_account_id(skat))

        with sdk.connected() as session, session.listening(tools_list_changed=True) as events:
            on_the_apps_worker(
                skat, skat.tables.free_held_chair, TableId(table_id), agent_account_id(skat), nullcontext(True)
            )
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
            timedelta(minutes=10),
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
