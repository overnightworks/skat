import itertools
import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from skat.engine.bidding import VALID_BIDS
from skat.web.auction import TABLE_AUCTION_SUFFIX
from skat.web.declaring import TABLE_DECLARATION_SUFFIX
from skat.web.mcp import PLAY_CARD_TOOL, READ_TABLE_TOOL
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.tables import TABLE_SIT_SUFFIX, TABLES_PATH
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import AddressedSession
from tests.e2e.support.people import DESKTOP, McpAgent
from tests.e2e.support.tables import open_new_table, sit_in, table_id_of, watch
from tests.support.signed_in import seed_member

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from playwright.sync_api import Page

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

AGENT_SEAT = 3
FELT_CARD = ".trick .laid"
command_numbers = itertools.count(1)


def next_command_id() -> str:
    return f"agent-plays-{next(command_numbers):04d}"


def step(session: AddressedSession, api_path: str, suffix: str, **fields: object) -> dict[str, Any]:
    version = json.loads(session.get(api_path))["version"]
    body = {"command_id": next_command_id(), "version": version, **fields}
    return json.loads(session.post(f"{api_path}{suffix}", body))


def play_until_the_agents_turn(
    sessions: Mapping[int, AddressedSession], api_path: str, seat_at: Mapping[str, int]
) -> None:
    step(sessions[seat_at["middlehand"]], api_path, TABLE_AUCTION_SUFFIX, action="bid", value=VALID_BIDS[-1])
    step(sessions[seat_at["forehand"]], api_path, TABLE_AUCTION_SUFFIX, action="pass")
    step(sessions[seat_at["rearhand"]], api_path, TABLE_AUCTION_SUFFIX, action="pass")
    step(
        sessions[seat_at["middlehand"]],
        api_path,
        TABLE_DECLARATION_SUFFIX,
        action="declare",
        game="herz",
        hand=True,
        ouvert=False,
        announcement="none",
    )
    turn_seat = json.loads(sessions[1].get(api_path))["hand"]["playing"]["turn_seat"]
    while turn_seat != AGENT_SEAT:
        legal = json.loads(sessions[turn_seat].get(api_path))["hand"]["playing"]["legal_cards"]
        played = step(sessions[turn_seat], api_path, TABLE_CARD_SUFFIX, **legal[0])
        turn_seat = played["hand"]["playing"]["turn_seat"]


def test_an_agents_card_lands_in_the_trick_a_person_sees(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    agent = McpAgent(e2e_server, "agent-subject-mozart")
    agent.request("tools/list")
    account = e2e_server.stores.accounts.get(agent.subject)
    assert account is not None
    anna = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(anna, e2e_server)
    ben = record_page_errors(open_person(username="ben", **DESKTOP), page_errors)
    watch(ben, e2e_server, path)
    sit_in(ben, 2)
    expect(ben.locator(".chair[data-seat='2'] .plate")).to_contain_text("ben")
    api_path = f"{TABLES_PATH}/{table_id_of(path)}"
    sessions = {
        1: AddressedSession(e2e_server, member_of(anna)),
        2: AddressedSession(e2e_server, member_of(ben)),
        AGENT_SEAT: AddressedSession(e2e_server, seed_member(e2e_server.stores, e2e_server.config, account=account)),
    }
    # Sitting is no tool yet, so the agent sits like a person with the cookie session of its account.
    sit_body = {"command_id": next_command_id(), "seat": AGENT_SEAT}
    sat = json.loads(sessions[AGENT_SEAT].post(f"{api_path}{TABLE_SIT_SUFFIX}", sit_body))
    assert "chairs" in sat
    chairs = json.loads(sessions[1].get(api_path))["chairs"]
    seat_at = {chair["hand"]["position"]: chair["seat"] for chair in chairs}
    play_until_the_agents_turn(sessions, api_path, seat_at)

    failed, text = agent.call(READ_TABLE_TOOL, table_id=table_id_of(path))
    view = json.loads(text)
    legal = view["hand"]["playing"]["legal_cards"]
    played_failed, played_text = agent.call(
        PLAY_CARD_TOOL, table_id=table_id_of(path), command_id=next_command_id(), version=view["version"], **legal[0]
    )

    assert not failed
    assert not played_failed, played_text
    for person in (anna, ben):
        card_on_the_felt = person.locator(f"{FELT_CARD}[data-seat='{AGENT_SEAT}'] .card-face")
        expect(card_on_the_felt).to_have_attribute("data-suit", legal[0]["suit"])
        expect(card_on_the_felt).to_have_attribute("data-rank", legal[0]["rank"])
