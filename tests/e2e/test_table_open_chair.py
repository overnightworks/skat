"""A chair of a running hand is open: every page draws the phase's plaque over the wait and no step, a tap on the free
chair asks before it sits, and the others read who left and who plays on.
"""

import itertools
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.calling import AGENT_ADDERS_GROUP
from skat.web.seating import TABLE_STAND_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.declaring import DeclaringTable, button_of
from tests.e2e.support.hands import TURN_CHAIR, deal_playing_table
from tests.e2e.support.kit_words import kit_text
from tests.e2e.support.listening_agent import ListeningAgent
from tests.e2e.support.people import DESKTOP, FORM_FACTORS, WIDTHS
from tests.e2e.support.tables import open_new_table, plate_of, sit_in, watch

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

KREUZ = text(SOURCE_LANGUAGE, "game.kreuz")
BIDDING = text(SOURCE_LANGUAGE, "table.bidding")
BID_VALUE = text(SOURCE_LANGUAGE, "table.bidValue")
WAITING = text(SOURCE_LANGUAGE, "table.waitingForPlayers")
SIT_QUESTION = text(SOURCE_LANGUAGE, "table.sitQuestion")
SIT_DOWN = text(SOURCE_LANGUAGE, "table.sitDown")
CANCEL = text(SOURCE_LANGUAGE, "table.sitQuestionCancel")
TAKE_SKAT = text(SOURCE_LANGUAGE, "declare.takeSkat")
SEAT_FREE = text(SOURCE_LANGUAGE, "table.seatFree")
COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
CALL_PILL = text(SOURCE_LANGUAGE, "agents.pill")
LEGAL_CARD = ".own-hand .card.ok"
BID_CONTROLS = ".bid"
INVITATION_WITHIN_SECONDS = 15
command_numbers = itertools.count(1)


def line_of(name: str) -> str:
    """The question's line for a name that takes the plain genitive."""
    return text(SOURCE_LANGUAGE, "table.takeOverNamed", name=name)


def left_notice(name: str) -> str:
    return text(SOURCE_LANGUAGE, "table.agentLeft", name=name)


def plays_on_notice(name: str) -> str:
    return text(SOURCE_LANGUAGE, "table.playsOn", name=name)


def stand_up_through_the_api(table: DeclaringTable, seat: int) -> None:
    table.sessions[seat].post(
        f"{table.api_path}{TABLE_STAND_SUFFIX}", {"command_id": f"stand-{next(command_numbers):04d}"}
    )


def expect_the_wait(person: Page, title: str) -> None:
    expect(person.locator(".plaque")).to_contain_text(title)
    expect(person.locator(".plaque")).to_contain_text(WAITING)
    expect(person.locator(TURN_CHAIR)).to_have_count(0)


def expect_no_scroll_sideways(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_person_stands_up_mid_game_and_a_watcher_asks_then_sits_and_the_others_read_who_plays_on(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor)
    leaver_seat = table.seat_at["rearhand"]
    leaver_name = table.names[leaver_seat]
    others = [person for seat, person in table.pages.items() if seat != leaver_seat]
    others_seat = next(seat for seat in table.pages if seat != leaver_seat)
    watcher = table.watcher

    stand_up_through_the_api(table.declaring, leaver_seat)

    for person in (*others, watcher):
        expect_the_wait(person, KREUZ)
        expect(person.locator(LEGAL_CARD)).to_have_count(0)
        expect(person.get_by_text(left_notice(leaver_name))).to_have_count(0)
        expect_no_scroll_sideways(person)
    free_chair = watcher.locator(f".chair[data-seat='{leaver_seat}']")
    expect(free_chair.locator(".fan-spot")).to_have_count(1)
    free_chair.get_by_role("button", name=SIT_DOWN).click()
    question = watcher.get_by_role("dialog", name=SIT_QUESTION)
    expect(question).to_contain_text(line_of(leaver_name))
    expect_no_scroll_sideways(watcher)

    button_of(watcher, CANCEL).click()

    expect(question).to_have_count(0)
    expect(plate_of(watcher, leaver_seat)).to_have_text(SEAT_FREE)

    free_chair.get_by_role("button", name=SIT_DOWN).click()
    question.get_by_role("button", name=SIT_DOWN).click()

    expect(watcher.locator(".chair.mine")).to_have_attribute("data-seat", str(leaver_seat))
    sitter_name = table.view(others_seat)["chairs"][leaver_seat - 1]["occupant_name"]
    for person in others:
        expect(person.get_by_text(plays_on_notice(sitter_name))).to_be_visible()
        expect(person.locator(".plaque")).not_to_contain_text(WAITING)
    expect(watcher.get_by_text(plays_on_notice(sitter_name))).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_person_who_stood_up_is_refused_another_open_chair_by_the_dialog_and_stays_unseated(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    # The browser logs the 409 of the refused sit as a console error; the refusal is the point of this test.
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, console=False)
    former_holder_seat = table.seat_at["rearhand"]
    other_seat = table.seat_at["middlehand"]
    former_holder = table.pages[former_holder_seat]

    stand_up_through_the_api(table.declaring, former_holder_seat)
    stand_up_through_the_api(table.declaring, other_seat)

    former_holder.locator(f".chair[data-seat='{other_seat}']").get_by_role("button", name=SIT_DOWN).click()
    former_holder.get_by_role("dialog", name=SIT_QUESTION).get_by_role("button", name=SIT_DOWN).click()

    expect(former_holder.get_by_role("status").filter(has_text=COMMAND_FAILED)).to_be_visible()
    expect(former_holder.locator(".chair.mine")).to_have_count(0)
    expect(plate_of(former_holder, other_seat)).to_have_text(SEAT_FREE)


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_person_stands_up_after_the_auction_and_the_declarer_reads_the_value_over_the_wait_with_no_control(
    deal_a_declaring_table: Callable[..., DeclaringTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    leaver_seat = next(seat for seat, session in table.sessions.items() if seat != table.declarer_seat)

    stand_up_through_the_api(table, leaver_seat)

    for person in (table.declarer, table.watcher):
        expect(person.locator(".plaque")).to_contain_text(BID_VALUE)
        expect(person.locator(".plaque")).to_contain_text(WAITING)
        expect(person.locator(TURN_CHAIR)).to_have_count(0)
    expect(button_of(table.declarer, TAKE_SKAT)).to_have_count(0)


@pytest.mark.usefixtures("realm_reusing_refresh_tokens")
@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_an_agent_sent_away_during_the_auction_leaves_the_plaque_over_the_wait_and_the_others_read_it_once(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    felix = record_page_errors(
        open_person(username="felix-sends-nova", groups=(AGENT_ADDERS_GROUP,), **DESKTOP), page_errors
    )
    path = open_new_table(felix, e2e_server)
    ben = record_page_errors(open_person(username="ben-stays", **form_factor), page_errors)
    watch(ben, e2e_server, path)
    sit_in(ben, 2)
    agent = ListeningAgent(e2e_server, member_of(felix).account.id, "Nova", "agent-subject-nova-open-chair")
    try:
        felix.get_by_role("button", name=CALL_PILL).click()
        felix.get_by_role("button", name=kit_text("agent.callLabel", name="Nova")).click()
        agent.accept(agent.invitation_within(felix, INVITATION_WITHIN_SECONDS))
        expect(felix.locator(".chair .mark.pos")).to_have_count(3)

        felix.get_by_role("button", name=kit_text("agent.askToLeaveLabel", name="Nova")).click()

        for person in (felix, ben):
            expect_the_wait(person, BIDDING)
            expect(person.locator(BID_CONTROLS)).to_have_count(0)
            expect(person.get_by_text(left_notice("Nova"))).to_be_visible()
    finally:
        agent.close()
