"""The seated players vote on the page to abort a hand while a chair of it is open: the strip's key takes two taps, the
others read the ask and answer it, and the hand ends at the majority with the felt empty.
"""

from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import button_of
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import PHONE, WIDTHS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

ABORT = text(SOURCE_LANGUAGE, "table.abort")
ABORT_SURE = text(SOURCE_LANGUAGE, "table.abortSure")
WAIT = text(SOURCE_LANGUAGE, "table.abortWait")
ABORTED = text(SOURCE_LANGUAGE, "table.aborted")
WAITING_FOR = text(SOURCE_LANGUAGE, "table.waitingFor")
NO_ANSWER_YET = text(SOURCE_LANGUAGE, "table.noAnswerYet")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
KEY = ".copy.abort"
ASK = ".plaque.ask"
ARMED_RUN_OUT_SECONDS = 3
RUN_OUT_TIMEOUT_MILLISECONDS = 3 * ARMED_RUN_OUT_SECONDS * 1000


def wants_to_abort(name: str) -> str:
    return text(SOURCE_LANGUAGE, "table.wantsToAbort", name=name)


@pytest.fixture
def deal_a_waiting_hand(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., tuple[PlayingTable, Page, Page]]:
    """A game in play whose rearhand has stood up: the table with its two seated pages, who proposes and who answers."""

    def deal(form_factor: dict[str, Any]) -> tuple[PlayingTable, Page, Page]:
        table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor)
        leaver_seat = table.seat_at["rearhand"]
        table.stand_up_through_the_api(leaver_seat)
        proposer_seat, answerer_seat = (seat for seat in table.pages if seat != leaver_seat)
        proposer, answerer = table.pages[proposer_seat], table.pages[answerer_seat]
        for person in (proposer, answerer):
            expect(person.locator(KEY)).to_be_visible()
        return table, proposer, answerer

    return deal


def expect_nothing_to_overflow(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    viewport = person.viewport_size
    assert viewport is not None
    for part in person.locator(f"{KEY}, {ASK}, {ASK} button").all():
        box = part.bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= viewport["width"]


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_person_taps_the_key_twice_the_other_agrees_and_the_hand_ends_aborted(
    deal_a_waiting_hand: Callable[..., tuple[PlayingTable, Page, Page]],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table, proposer, answerer = deal_a_waiting_hand(form_factor)
    proposer_name = table.names[table.seat_of(proposer)]
    answerer_seat = table.seat_of(answerer)
    answerer_name = table.names[answerer_seat]
    expect_nothing_to_overflow(proposer)
    expect(table.watcher.locator(KEY)).to_have_count(0)

    proposer.locator(KEY).click()

    expect(proposer.locator(KEY)).to_contain_text(ABORT_SURE)
    expect(answerer.locator(ASK)).to_have_count(0)
    expect_nothing_to_overflow(proposer)

    proposer.locator(KEY).click()

    expect(answerer.locator(ASK)).to_contain_text(wants_to_abort(proposer_name))
    expect(button_of(answerer, ABORT)).to_be_visible()
    expect(button_of(answerer, WAIT)).to_be_visible()
    expect(proposer.locator(ASK)).to_contain_text(f"{WAITING_FOR} {answerer_name}")
    expect(proposer.locator(f"{ASK} button")).to_have_count(0)
    expect(proposer.locator(KEY)).to_have_count(0)
    expect(
        proposer.locator(f".chair[data-seat='{answerer_seat}'] .mark.unanswered[title='{NO_ANSWER_YET}']")
    ).to_have_count(1)
    expect(table.watcher.locator(ASK)).to_contain_text(wants_to_abort(proposer_name))
    expect(table.watcher.locator(f"{ASK} button")).to_have_count(0)
    for person in (proposer, answerer):
        expect_nothing_to_overflow(person)

    button_of(answerer, ABORT).click()

    for person in (proposer, answerer, table.watcher):
        expect(person.locator(".plaque")).to_contain_text(ABORTED)
        expect(person.locator(ASK)).to_have_count(0)
        expect(person.locator(KEY)).to_have_count(0)
        expect(person.locator(".fan-spot")).to_have_count(0)
    for person in (proposer, answerer):
        expect(button_of(person, STAND_UP)).to_be_visible()
    view = table.view(answerer_seat)
    assert view["hand"] is None
    assert view["aborted"] == {"next_dealer_seat": None}
    assert view["result"] is None
    assert page_errors == []


def test_a_no_takes_the_proposal_away_and_the_key_is_offered_again(
    deal_a_waiting_hand: Callable[..., tuple[PlayingTable, Page, Page]], page_errors: list[str]
) -> None:
    table, proposer, answerer = deal_a_waiting_hand(PHONE)
    proposer.locator(KEY).click()
    proposer.locator(KEY).click()
    expect(answerer.locator(ASK)).to_be_visible()

    button_of(answerer, WAIT).click()

    for person in (proposer, answerer):
        expect(person.locator(ASK)).to_have_count(0)
        expect(person.locator(KEY)).to_contain_text(ABORT)
    assert table.view(table.seat_of(answerer))["hand"]["abort"] is None
    assert page_errors == []


def test_the_armed_key_runs_out_after_three_seconds_and_sends_nothing(
    deal_a_waiting_hand: Callable[..., tuple[PlayingTable, Page, Page]], page_errors: list[str]
) -> None:
    table, proposer, answerer = deal_a_waiting_hand(PHONE)

    proposer.locator(KEY).click()

    expect(proposer.locator(KEY)).to_contain_text(ABORT_SURE)
    expect(proposer.locator(KEY)).not_to_contain_text(ABORT_SURE, timeout=RUN_OUT_TIMEOUT_MILLISECONDS)
    expect(proposer.locator(KEY)).to_contain_text(ABORT)
    expect(answerer.locator(ASK)).to_have_count(0)
    assert table.view(table.seat_of(answerer))["hand"]["abort"] is None
    assert page_errors == []
