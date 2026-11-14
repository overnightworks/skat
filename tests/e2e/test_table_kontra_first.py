import re
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import button_of
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.kontra import (
    BIDDERS_ONLY_OPTIONS,
    ContestedTable,
    LeadingTable,
    expect_nothing_to_overflow,
)
from tests.e2e.support.people import WIDTHS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

KONTRA = text(SOURCE_LANGUAGE, "kontra.kontra")
RE = text(SOURCE_LANGUAGE, "kontra.re")
YOU = text(SOURCE_LANGUAGE, "kontra.you")
WAIT_LINE = ".plaque .game.gives"
DIMMED_HAND = ".controls.held"
DIMMED_FAN = ".fan.dim"
DIMMED_OPEN_CARD = ".open .card"
GIVE_UP_KEY = ".copy.give-up"
ROUND_KEY = re.compile(r"\bround\b")
TURN_CHAIR = ".chair.turn"


def decline_of(word: str) -> str:
    return text(SOURCE_LANGUAGE, "kontra.decline", word=word)


FIRST_CARD_OPTIONS = {**BIDDERS_ONLY_OPTIONS, "deadline": "first-card"}


class FirstCardTable(ContestedTable):
    """The forehand bid and leads; the first card waits for its word."""

    kontra_options: ClassVar[dict[str, str]] = FIRST_CARD_OPTIONS


class LeadingFirstCardTable(LeadingTable):
    """The declarer leads; the first card waits for the middlehand's word."""

    kontra_options: ClassVar[dict[str, str]] = FIRST_CARD_OPTIONS


def owing_page(table: PlayingTable, position: str) -> Page:
    return table.pages[table.seat_at[position]]


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_seat_owing_a_word_declines_it_and_every_other_page_reads_the_wait_from_the_line_and_the_dimmed_cards(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, declaring=FirstCardTable)
    owing = owing_page(table, "forehand")
    others = [owing_page(table, "middlehand"), owing_page(table, "rearhand"), table.watcher]
    forehand_name = table.names[table.seat_at["forehand"]]

    expect(button_of(owing, KONTRA)).to_be_visible()
    expect(button_of(owing, decline_of(KONTRA))).to_be_visible()
    expect(owing.locator(WAIT_LINE)).to_contain_text(YOU)
    expect(owing.locator(DIMMED_HAND)).to_have_count(1)
    expect(owing.locator(f"{DIMMED_HAND} .own-hand .card").first).to_have_css("filter", re.compile("brightness"))
    expect_nothing_to_overflow(owing)
    expect(owing.locator(GIVE_UP_KEY)).not_to_have_class(ROUND_KEY)
    for person in others:
        expect(person.locator(WAIT_LINE)).to_contain_text(forehand_name)
        expect(person.locator(TURN_CHAIR)).to_have_attribute("data-seat", str(table.seat_at["forehand"]))
        expect(person.locator(".copy.no-word")).to_have_count(0)
        expect(person.locator(DIMMED_HAND)).to_have_count(0)
        expect(person.locator(DIMMED_FAN)).to_have_count(1)

    button_of(owing, decline_of(KONTRA)).click()

    for person in table.everyone:
        expect(person.locator(WAIT_LINE)).to_have_count(0)
        expect(person.locator(DIMMED_HAND)).to_have_count(0)
    table.play_through_the_api(sorted(table.legal_cards(table.seat_at["forehand"]))[0])
    assert table.turn_seat() != table.seat_at["forehand"]
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_after_a_kontra_the_wait_moves_to_the_declarer_who_answers_with_re_or_declines(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, declaring=FirstCardTable)
    declarer = table.pages[table.declarer_seat]
    declarer_name = table.names[table.declarer_seat]

    button_of(owing_page(table, "forehand"), KONTRA).click()

    expect(button_of(declarer, RE)).to_be_visible()
    expect(button_of(declarer, decline_of(RE))).to_be_visible()
    expect_nothing_to_overflow(declarer)
    expect(declarer.locator(GIVE_UP_KEY)).not_to_have_class(ROUND_KEY)
    expect(declarer.locator(WAIT_LINE)).to_contain_text(YOU)
    for person in (owing_page(table, "forehand"), owing_page(table, "rearhand"), table.watcher):
        expect(person.locator(WAIT_LINE)).to_contain_text(declarer_name)

    button_of(declarer, decline_of(RE)).click()

    for person in table.everyone:
        expect(person.locator(WAIT_LINE)).to_have_count(0)
    assert page_errors == []


def declare_grand_ouvert_hand(table: LeadingFirstCardTable) -> None:
    table.declare_through_the_api(action="declare", game="grand", hand=True, ouvert=True, announcement="schwarz")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_open_declarer_who_leads_shows_dimmed_cards_to_the_other_pages_until_the_wait_ends(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = LeadingFirstCardTable(open_person, e2e_server, member_of, page_errors, form_factor)
    declare_grand_ouvert_hand(table)
    others = [*table.others, table.watcher]
    middlehand = next(chair["seat"] for chair in table.chairs() if chair["hand"]["position"] == "middlehand")
    open_cards = f".chair[data-seat='{table.declarer_seat}'] {DIMMED_OPEN_CARD}"

    for person in others:
        expect(person.locator(TURN_CHAIR)).to_have_attribute("data-seat", str(middlehand))
        expect(person.locator(open_cards).first).to_have_css("filter", re.compile("brightness"))

    button_of(table.people[middlehand], decline_of(KONTRA)).click()

    for person in others:
        expect(person.locator(WAIT_LINE)).to_have_count(0)
        expect(person.locator(open_cards).first).not_to_have_css("filter", re.compile("brightness"))
    assert page_errors == []
