from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.people import WIDTHS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

FELT_FACE = ".trick .laid .face"
LANDING = "land"
STILL = "none"
MOTION = "no-preference"
REDUCED_MOTION = "reduce"


@pytest.fixture
def deal_a_playing_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    def deal(form_factor: dict[str, Any]) -> PlayingTable:
        return deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, game="kreuz")

    return deal


def open_watcher_with_motion(
    open_person: Callable[..., Page], page_errors: list[str], table: PlayingTable, form_factor: dict[str, Any]
) -> Page:
    watcher = record_page_errors(open_person(reduced_motion=MOTION, **form_factor), page_errors)
    watcher.goto(table.watcher.url)
    expect(watcher.locator(".chair")).to_have_count(3)
    return watcher


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_card_played_while_the_page_watches_lands_on_the_felt(
    deal_a_playing_table: Callable[..., PlayingTable],
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_playing_table(form_factor)
    watcher = open_watcher_with_motion(open_person, page_errors, table, form_factor)

    table.play_out(1)

    expect(watcher.locator(FELT_FACE)).to_have_count(1)
    expect(watcher.locator(FELT_FACE)).to_have_css("animation-name", LANDING)
    expect(table.watcher.locator(FELT_FACE)).to_have_css("animation-name", STILL)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_cards_a_page_did_not_see_played_stand_still_and_the_next_card_lands(
    deal_a_playing_table: Callable[..., PlayingTable],
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_playing_table(form_factor)
    table.play_out(1)
    joined = open_watcher_with_motion(open_person, page_errors, table, form_factor)
    expect(joined.locator(FELT_FACE)).to_have_css("animation-name", STILL)

    joined.reload()
    expect(joined.locator(".chair")).to_have_count(3)
    expect(joined.locator(FELT_FACE)).to_have_css("animation-name", STILL)

    table.play_out(1)

    expect(joined.locator(FELT_FACE)).to_have_count(2)
    expect(joined.locator(FELT_FACE).last).to_have_css("animation-name", LANDING)
    expect(joined.locator(FELT_FACE).first).to_have_css("animation-name", STILL)
    assert page_errors == []
