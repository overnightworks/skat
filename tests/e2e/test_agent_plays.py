import itertools
import json
import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from skat.engine.bidding import VALID_BIDS
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_PASS_SUFFIX, TABLE_AUCTION_PLAY_SUFFIX
from skat.web.declaring import TABLE_DECLARING_DECLARE_SUFFIX
from skat.web.kontra import TABLE_KONTRA_SUFFIX
from skat.web.mcp import (
    AUCTION_BID_TOOL,
    AUCTION_PASS_TOOL,
    AUCTION_PLAY_TOOL,
    DECLARE_GAME_TOOL,
    PLAY_CARD_TOOL,
    READ_TABLE_TOOL,
    SAY_KONTRA_TOOL,
    SIT_DOWN_TOOL,
)
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE
from skat.web.words import text as word_text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import AddressedSession, leave_the_last_trick_on_the_felt
from tests.e2e.support.kontra import KONTRA_OPTIONS
from tests.e2e.support.people import DESKTOP, McpAgent
from tests.e2e.support.tables import open_new_table, open_table_with_options, sit_in, table_id_of, watch
from tests.support.signed_in import account_of, seed_member

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from playwright.sync_api import Page

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

AGENT_SEAT = 3
AGENT_NAME = "Mozart"
FELT_CARD = ".trick .laid"
command_numbers = itertools.count(1)


def next_command_id() -> str:
    return f"agent-plays-{next(command_numbers):04d}"


def step(session: AddressedSession, api_path: str, suffix: str, **fields: object) -> dict[str, Any]:
    version = json.loads(session.get(api_path))["version"]
    body = {"command_id": next_command_id(), "version": version, **fields}
    return json.loads(session.post(f"{api_path}{suffix}", body))


def take_step(
    sessions: Mapping[int, AddressedSession],
    api_path: str,
    seat: int,
    agent: McpAgent,
    suffix: str,
    tool: str,
    **fields: object,
) -> None:
    """The step at `seat`: through the agent's tool when the agent sits there, else through the person's route."""
    if seat != AGENT_SEAT:
        step(sessions[seat], api_path, suffix, **fields)
        return
    version = json.loads(sessions[seat].get(api_path))["version"]
    failed, text = agent.call(
        tool, table_id=api_path.rsplit("/", 1)[1], command_id=next_command_id(), version=version, **fields
    )
    assert not failed, text


def let_the_agent_declare(
    sessions: Mapping[int, AddressedSession], api_path: str, seat_at: Mapping[str, int], agent: McpAgent
) -> None:
    """The seat the lot gave the agent wins the auction with the highest bid there is and declares Hand."""
    winner = next(position for position, seat in seat_at.items() if seat == AGENT_SEAT)
    bid = (TABLE_AUCTION_BID_SUFFIX, AUCTION_BID_TOOL, {"value": VALID_BIDS[-1]})
    drop = (TABLE_AUCTION_PASS_SUFFIX, AUCTION_PASS_TOOL, {})
    auction = {
        "middlehand": [("middlehand", bid), ("forehand", drop), ("rearhand", drop)],
        "forehand": [
            ("middlehand", drop),
            ("rearhand", drop),
            ("forehand", (TABLE_AUCTION_PLAY_SUFFIX, AUCTION_PLAY_TOOL, {})),
        ],
        "rearhand": [("middlehand", drop), ("rearhand", bid), ("forehand", drop)],
    }[winner]
    for position, (suffix, tool, fields) in auction:
        take_step(sessions, api_path, seat_at[position], agent, suffix, tool, **fields)
    take_step(
        sessions,
        api_path,
        AGENT_SEAT,
        agent,
        TABLE_DECLARING_DECLARE_SUFFIX,
        DECLARE_GAME_TOOL,
        game="herz",
        hand=True,
        ouvert=False,
        announcement="none",
    )


def play_until_the_agents_turn(
    sessions: Mapping[int, AddressedSession], api_path: str, seat_at: Mapping[str, int], agent: McpAgent
) -> None:
    """The agent declares Hand, then each seat before it plays its first legal card."""
    let_the_agent_declare(sessions, api_path, seat_at, agent)
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
    agent = McpAgent(e2e_server, "agent-subject-mozart-plays")
    agent.request("tools/list")
    account = account_of(e2e_server.stores, agent.subject)
    assert account is not None
    anna = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)
    path = open_new_table(anna, e2e_server)
    ben = record_page_errors(open_person(username="ben", **DESKTOP), page_errors)
    watch(ben, e2e_server, path)
    sit_in(ben, 2)
    expect(ben.locator(".chair[data-seat='2'] .plate")).to_contain_text(word_text(SOURCE_LANGUAGE, "table.sideYou"))
    api_path = f"{TABLES_PATH}/{table_id_of(path)}"
    sessions = {
        1: AddressedSession(e2e_server, member_of(anna)),
        2: AddressedSession(e2e_server, member_of(ben)),
        AGENT_SEAT: AddressedSession(e2e_server, seed_member(e2e_server.stores, e2e_server.config, account=account)),
    }
    sat_failed, sat_text = agent.call(
        SIT_DOWN_TOOL, table_id=table_id_of(path), seat=AGENT_SEAT, command_id=next_command_id()
    )
    assert not sat_failed
    assert "chairs" in json.loads(sat_text)
    for page in (anna, ben):
        expect(page.locator(f".chair[data-seat='{AGENT_SEAT}'] .plate")).to_contain_text(AGENT_NAME)
    chairs = json.loads(sessions[1].get(api_path))["chairs"]
    seat_at = {chair["hand"]["position"]: chair["seat"] for chair in chairs}
    play_until_the_agents_turn(sessions, api_path, seat_at, agent)
    leave_the_last_trick_on_the_felt([anna, ben])

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


def test_a_word_an_agent_says_stamps_the_felt_with_the_agents_mark(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    agent = McpAgent(e2e_server, "agent-subject-mozart-says-re")
    agent.request("tools/list")
    account = account_of(e2e_server.stores, agent.subject)
    assert account is not None
    anna = record_page_errors(open_person(username="anna-hears-re", **DESKTOP), page_errors)
    opener = AddressedSession(e2e_server, member_of(anna))
    path = open_table_with_options(anna, e2e_server, opener, {"kontra": KONTRA_OPTIONS})
    ben = record_page_errors(open_person(username="ben-hears-re", **DESKTOP), page_errors)
    watch(ben, e2e_server, path)
    sit_in(ben, 2)
    api_path = f"{TABLES_PATH}/{table_id_of(path)}"
    sessions = {
        1: opener,
        2: AddressedSession(e2e_server, member_of(ben)),
        AGENT_SEAT: AddressedSession(e2e_server, seed_member(e2e_server.stores, e2e_server.config, account=account)),
    }
    sat_failed, _ = agent.call(SIT_DOWN_TOOL, table_id=table_id_of(path), seat=AGENT_SEAT, command_id=next_command_id())
    assert not sat_failed
    chairs = json.loads(sessions[1].get(api_path))["chairs"]
    seat_at = {chair["hand"]["position"]: chair["seat"] for chair in chairs}
    let_the_agent_declare(sessions, api_path, seat_at, agent)
    # Before any card, an opponent says Kontra, which the declaring agent may answer.
    take_step(sessions, api_path, 1, agent, TABLE_KONTRA_SUFFIX, SAY_KONTRA_TOOL, word="kontra")

    take_step(sessions, api_path, AGENT_SEAT, agent, TABLE_KONTRA_SUFFIX, SAY_KONTRA_TOOL, word="re")

    said = word_text(SOURCE_LANGUAGE, "kontra.saidBy", name=AGENT_NAME, word=word_text(SOURCE_LANGUAGE, "kontra.re"))
    for person in (anna, ben):
        stamp = person.get_by_role("img", name=said)
        expect(stamp).to_be_visible()
        expect(stamp).to_have_class(re.compile(r"\bagent\b"))
        expect(stamp.locator(".by")).to_have_text("")
    assert page_errors == []
