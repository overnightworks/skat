import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect

from skat.engine.bidding import VALID_BIDS
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_HOLD_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.kontra import TABLE_KONTRA_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import DeclaringTable, button_of, reload_and_wait
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import DESKTOP, PHONE, WIDTHS
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.tables import open_table_with_options

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

KONTRA = text(SOURCE_LANGUAGE, "kontra.kontra")
RE = text(SOURCE_LANGUAGE, "kontra.re")
COMMAND_FAILED = text(SOURCE_LANGUAGE, "kontra.commandFailed")
KEY = ".copy.kontra"
STAMP = ".callout"
NEAR_CARD = ".laid.near .face"
SECOND_LINE = ".plaque .pushes"
# Only an opponent who bid says Kontra, and the declarer answers with Re.
KONTRA_OPTIONS = {"kontra": {"sayer": "bidders-only", "reach": "kontra-re", "deadline": "own-card"}}


class KontraTable(DeclaringTable):
    """A table opened through the API with Kontra and Re."""

    @staticmethod
    def _open_table(
        opener: Page, server: RunningServer, member_of: Callable[[Page], SeededMember], *, running_points: bool
    ) -> str:
        assert not running_points
        return open_table_with_options(opener, server, RawSession(server, member_of(opener)), KONTRA_OPTIONS)


class ContestedTable(KontraTable):
    """The forehand holds at the first bid and drops out at the second; the rearhand passes at once."""

    def _win_the_auction(self, seat_at: dict[str, int]) -> None:
        self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=VALID_BIDS[0])
        self.step(seat_at["forehand"], TABLE_AUCTION_HOLD_SUFFIX)
        self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=VALID_BIDS[-1])
        self.step(seat_at["forehand"], TABLE_AUCTION_PASS_SUFFIX)
        self.step(seat_at["rearhand"], TABLE_AUCTION_PASS_SUFFIX)


class LeadingTable(KontraTable):
    """The forehand outbids the middlehand, so the declarer leads and the middlehand may say Kontra."""

    declarer_position = "forehand"

    def _win_the_auction(self, seat_at: dict[str, int]) -> None:
        self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=VALID_BIDS[0])
        self.step(seat_at["forehand"], TABLE_AUCTION_HOLD_SUFFIX)
        self.step(seat_at["middlehand"], TABLE_AUCTION_PASS_SUFFIX)
        self.step(seat_at["rearhand"], TABLE_AUCTION_PASS_SUFFIX)


@pytest.fixture
def deal_a_kontra_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    """A declared Kreuz game at a table with Kontra, before the first card."""

    def deal(
        form_factor: dict[str, Any], *, console: bool = True, declaring: type[DeclaringTable] = ContestedTable
    ) -> PlayingTable:
        return deal_playing_table(
            open_person,
            e2e_server,
            member_of,
            page_errors,
            form_factor,
            console=console,
            declaring=declaring,
        )

    return deal


def says_kontra(table: PlayingTable) -> Page:
    """The page of the opponent who bid."""
    return table.pages[table.seat_at["forehand"]]


def passed_at_once(table: PlayingTable) -> Page:
    return table.pages[table.seat_at["rearhand"]]


def expect_every_page_to_show(table: PlayingTable, word: str, factor: int) -> None:
    for person in table.everyone:
        expect(person.locator(STAMP)).to_contain_text(word)
        expect(person.locator(SECOND_LINE)).to_have_text(
            text(SOURCE_LANGUAGE, "kontra.plaque", word=word, factor=str(factor))
        )


def expect_nothing_to_overflow(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    viewport = person.viewport_size
    assert viewport is not None
    for part in person.locator(f"{KEY}, {STAMP}").all():
        box = part.bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= viewport["width"]


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_opponent_who_bid_says_kontra_and_the_declarer_re_and_every_page_shows_each_word_and_the_factor(
    deal_a_kontra_table: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_kontra_table(form_factor)
    declarer = table.pages[table.declarer_seat]
    expect(button_of(says_kontra(table), KONTRA)).to_be_visible()
    expect_nothing_to_overflow(says_kontra(table))
    for person in (passed_at_once(table), declarer, table.watcher):
        expect(person.locator(KEY)).to_have_count(0)

    button_of(says_kontra(table), KONTRA).click()

    expect_every_page_to_show(table, KONTRA, 2)
    expect(says_kontra(table).locator(KEY)).to_have_count(0)
    expect(button_of(declarer, RE)).to_be_visible()
    expect_nothing_to_overflow(declarer)
    expect_nothing_to_overflow(table.watcher)
    expect(passed_at_once(table).locator(KEY)).to_have_count(0)

    button_of(declarer, RE).click()

    expect_every_page_to_show(table, RE, 4)
    for person in table.everyone:
        expect(person.locator(KEY)).to_have_count(0)
    assert page_errors == []


def test_the_stamp_lands_above_the_declarers_own_led_card_at_1280(
    deal_a_kontra_table: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_kontra_table(DESKTOP, declaring=LeadingTable)
    table.play_through_the_api(sorted(table.legal_cards(table.declarer_seat))[0])
    declarer = table.pages[table.declarer_seat]
    expect(declarer.locator(NEAR_CARD)).to_be_visible()

    button_of(table.pages[table.seat_at["middlehand"]], KONTRA).click()

    expect(declarer.locator(STAMP)).to_contain_text(KONTRA)
    stamp = declarer.locator(STAMP).bounding_box()
    card = declarer.locator(NEAR_CARD).bounding_box()
    assert stamp is not None
    assert card is not None
    assert stamp["y"] + stamp["height"] / 2 <= card["y"]
    assert page_errors == []


def test_a_reload_after_a_word_shows_the_plaque_and_no_second_stamp(
    deal_a_kontra_table: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_kontra_table(PHONE)
    button_of(says_kontra(table), KONTRA).click()
    expect(table.watcher.locator(STAMP)).to_be_visible()

    reload_and_wait(table.watcher)

    expect(table.watcher.locator(SECOND_LINE)).to_have_text(
        text(SOURCE_LANGUAGE, "kontra.plaque", word=KONTRA, factor="2")
    )
    expect(table.watcher.locator(STAMP)).to_have_count(0)
    assert page_errors == []


def test_the_stamp_leaves_the_felt_once_its_moment_has_passed(
    deal_a_kontra_table: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_kontra_table(PHONE)
    button_of(says_kontra(table), KONTRA).click()
    expect(table.watcher.locator(STAMP)).to_be_visible()

    expect(table.watcher.locator(STAMP)).to_have_count(0)

    expect(table.watcher.locator(SECOND_LINE)).to_have_text(
        text(SOURCE_LANGUAGE, "kontra.plaque", word=KONTRA, factor="2")
    )
    assert page_errors == []


def test_a_double_tap_sends_one_request(
    deal_a_kontra_table: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_kontra_table(PHONE)
    saying = says_kontra(table)
    sent: list[str] = []
    saying.on(
        "request", lambda request: sent.append(request.url) if request.url.endswith(TABLE_KONTRA_SUFFIX) else None
    )

    button_of(saying, KONTRA).dblclick()

    expect(saying.locator(KEY)).to_have_count(0)
    assert len(sent) == 1
    assert page_errors == []


def test_a_refused_word_shows_the_refusal_and_leaves_the_key_to_try_again_with_a_new_command_id(
    deal_a_kontra_table: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    # The browser logs the refused word as a console error; that refusal is the point of this test.
    table = deal_a_kontra_table(PHONE, console=False)
    saying = says_kontra(table)
    command_ids: list[str] = []

    def refuse_the_first(route: Route) -> None:
        command_ids.append(json.loads(route.request.post_data or "")["command_id"])
        if len(command_ids) == 1:
            route.fulfill(status=409, json={"reason": "stale-version"})
        else:
            route.continue_()

    saying.route(f"**{table.declaring.api_path}{TABLE_KONTRA_SUFFIX}", refuse_the_first)
    button_of(saying, KONTRA).click()

    expect(saying.locator(".note")).to_have_text(COMMAND_FAILED)
    button_of(saying, KONTRA).click()

    expect_every_page_to_show(table, KONTRA, 2)
    assert len(set(command_ids)) == 2
    assert page_errors == []


def test_the_key_takes_the_keyboard(deal_a_kontra_table: Callable[..., PlayingTable], page_errors: list[str]) -> None:
    table = deal_a_kontra_table(PHONE)
    saying = says_kontra(table)

    button_of(saying, KONTRA).focus()
    saying.keyboard.press("Enter")

    expect_every_page_to_show(table, KONTRA, 2)
    assert page_errors == []
