from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from skat.engine.bidding import VALID_BIDS
from skat.engine.tricks import CARDS_IN_A_GAME
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.ready import TABLE_READY_SUFFIX
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.hands import THEY, WE, PlayingTable, deal_playing_table
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.result_card import (
    BID_VALUE,
    CARD,
    EACH,
    LIST_BONUS,
    LOSES,
    LOST,
    MINUS,
    OVERBID,
    SPIEL,
    TIMES,
    WINS,
    WON,
    WORTH,
    YOU,
    expect_the_page_around_the_card,
    loosely,
)
from tests.e2e.support.tables import SIT_DOWN
from tests.e2e.support.words import catalog_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

WEITER = catalog_text("weiter")
STAND_UP = catalog_text("standUp")
COPY_LINK = catalog_text("copyLink")
WAITING_FOR = catalog_text("waitingFor")
AND = catalog_text("and")
COMMAND_FAILED = catalog_text("commandFailed")
SEAT_AWAY = catalog_text("seatAway")
SEAT_FREE = catalog_text("seatFree")
READY_MARK = ".mark.ready"
OWN_HAND_CARD = ".own-hand .card"
CARDS_IN_A_HAND = 10
LONG_NAMES = ("Bartholom\u00e4us-Maximilian-Ferdinand", "Maximiliane-Bartholom\u00e4a-Ferdinande")

PILL_HEIGHTS = (
    "bar => [...bar.children].filter(child => !child.matches('.link'))"
    ".map(child => child.getBoundingClientRect().height)"
)


class ModestBidTable(DeclaringTable):
    """The middlehand bids the lowest value, so the game declared lies above it and is never overbid."""

    def _win_the_auction(self, seat_at: dict[str, int]) -> None:
        self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=VALID_BIDS[0])
        self.step(seat_at["forehand"], TABLE_AUCTION_PASS_SUFFIX)
        self.step(seat_at["rearhand"], TABLE_AUCTION_PASS_SUFFIX)


HANDS = [pytest.param(DeclaringTable, id="overbid"), pytest.param(ModestBidTable, id="modest")]


@pytest.fixture
def deal_a_finished_hand(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    def deal(
        form_factor: dict[str, Any],
        *,
        declaring: type[DeclaringTable] = DeclaringTable,
        console: bool = True,
        joiners: tuple[str, str] = ("ben", "cleo"),
    ) -> PlayingTable:
        table = deal_playing_table(
            open_person,
            e2e_server,
            member_of,
            page_errors,
            form_factor,
            console=console,
            game="kreuz",
            declaring=declaring,
            joiners=joiners,
        )
        table.play_out(CARDS_IN_A_GAME)
        return table

    return deal


def with_minus(number: int) -> str:
    return f"{MINUS}{-number}" if number < 0 else str(number)


def signed(number: int) -> str:
    return with_minus(number) if number < 0 else f"+{number}"


def awaited(table: PlayingTable, ready: set[int]) -> str:
    return f" {AND} ".join(name for seat, name in table.names.items() if seat not in ready)


def role_of(table: PlayingTable, person: Page) -> str:
    if person is table.watcher:
        return "watcher"
    return "declarer" if person is table.pages[table.declarer_seat] else "opponent"


def expected_word(table: PlayingTable, person: Page) -> str:
    won = table.result()["won"]
    role = role_of(table, person)
    if role == "watcher":
        return f"{table.names[table.declarer_seat]} {WINS if won else LOSES}"
    return WON if won == (role == "declarer") else LOST


def expect_the_raise(card: Locator, result: dict[str, Any]) -> None:
    if result["overbid"]:
        expect(card.locator(".stamp")).to_have_text(OVERBID)
        expect(card.locator(".miss:not(.missed)")).to_have_text(
            f"{WORTH} {result['game_value']} < {BID_VALUE} {result['bid']} \u2192 {result['settled_value']}"
        )
    else:
        expect(card.locator(".stamp")).to_have_count(0)
        expect(card.locator(".miss:not(.missed)")).to_have_count(0)


def expect_the_rows(card: Locator, table: PlayingTable, person: Page, role: str, result: dict[str, Any]) -> None:
    rows = card.locator(".reck")
    expect(rows).to_have_count(3)
    for gain in result["gains"]:
        row = card.locator(f".reck[data-seat='{gain['seat']}']")
        expect(row.locator(".dl")).to_have_text(signed(gain["gain"]) if gain["gain"] else "0")
        own = role != "watcher" and person is table.pages[gain["seat"]]
        expect(row.locator(".nm")).to_have_text(YOU if own else table.names[gain["seat"]])
        expect(card.locator(f".reck.win[data-seat='{gain['seat']}']")).to_have_count(1 if gain["won"] else 0)


def expect_the_card(table: PlayingTable) -> None:
    """Every viewer reads the card as the answer counted it, from their own side."""
    result = table.result()
    for person in table.everyone:
        role = role_of(table, person)
        card = person.locator(CARD)
        expect(card).to_have_count(1)
        expect(card.locator("h3")).to_have_text(expected_word(table, person))
        expect(card.locator(".value")).to_have_text(signed(result["score"]))
        expect(card.locator(".x2")).to_have_count(1 if result["doubled"] else 0)
        expect(card.locator(".ladder > *")).to_have_count(len(result["levels"]) + 1)
        equation = [str(result["multiplier"]), TIMES, str(result["base_value"])]
        if result["doubled"]:
            equation += ["=", str(result["game_value"])]
        expect(card.locator(".eq")).to_have_text(loosely(*equation))
        expect(card.locator(".miss.missed")).to_have_count(1 if result["announcement_missed"] else 0)
        expect_the_raise(card, result)
        names = {"declarer": (YOU, THEY), "opponent": (table.names[table.declarer_seat], WE)}.get(
            role, (table.names[table.declarer_seat], THEY)
        )
        expect(card.locator(".sides .declarer")).to_have_text(f"{names[0]} {result['declarer_points']}")
        expect(card.locator(".sides .opponents")).to_have_text(f"{names[1]} {result['opponents_points']}")
        declarer_gain = next(gain for gain in result["gains"] if gain["seat"] == result["declarer_seat"])["gain"]
        opponent_gain = next(gain for gain in result["gains"] if gain["seat"] != result["declarer_seat"])["gain"]
        steps = [
            names[0],
            f"{SPIEL} {signed(result['score'])}",
            f"{LIST_BONUS} {signed(result['list_bonus'])}",
            f"= {signed(declarer_gain)}",
        ]
        if result["doubled"]:
            steps.append(f"\u00b7 {names[1]} {EACH} {signed(opponent_gain)}")
        expect(card.locator(".list")).to_have_text(loosely(*steps))
        expect_the_rows(card, table, person, role, result)


def expect_the_bars_inside_the_pages(table: PlayingTable) -> None:
    for person in table.everyone:
        bar = person.locator(".actions").bounding_box()
        assert bar is not None
        assert bar["x"] >= 0
        assert bar["x"] + bar["width"] <= person.evaluate("window.innerWidth")
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def expect_the_marks(table: PlayingTable, ready: set[int]) -> None:
    for person in table.everyone:
        expect(person.locator(".chair .mark.declarer")).to_have_count(1)
        expect(person.locator(f".chair[data-seat='{table.declarer_seat}'] .mark.declarer")).to_have_count(1)
        for seat in table.names:
            expect(person.locator(f".chair[data-seat='{seat}'] {READY_MARK}")).to_have_count(1 if seat in ready else 0)


def expect_the_buttons(table: PlayingTable, ready: set[int]) -> None:
    """The seated viewers' bars: „Weiter“ until they have tapped, then who is awaited; the watcher's has neither."""
    for seat, person in table.pages.items():
        bar = person.locator(".actions")
        assert bar.evaluate("bar => new Set([...bar.children].map(child => child.offsetTop)).size") == 1
        expect(bar.get_by_role("button", name=STAND_UP)).to_be_visible()
        expect(bar.get_by_role("button", name=COPY_LINK)).to_be_visible()
        if seat in ready:
            expect(bar.get_by_role("button", name=WEITER)).to_have_count(0)
            expect(bar.get_by_role("status")).to_have_text(f"{WAITING_FOR} {awaited(table, ready)}")
        else:
            expect(bar.get_by_role("button", name=WEITER)).to_be_visible()
    for name in (WEITER, STAND_UP):
        expect(table.watcher.locator(".actions").get_by_role("button", name=name)).to_have_count(0)


def reload_everyone(table: PlayingTable) -> None:
    for person in table.everyone:
        person.reload()
        expect(person.locator(".chair")).to_have_count(3)


@pytest.mark.parametrize("declaring", HANDS)
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_everyone_reads_the_result_and_the_three_taps_deal_the_next_hand(
    deal_a_finished_hand: Callable[..., PlayingTable],
    page_errors: list[str],
    form_factor: dict[str, Any],
    declaring: type[DeclaringTable],
) -> None:
    table = deal_a_finished_hand(form_factor, declaring=declaring)
    first, second = (seat for seat in table.names if seat != table.declarer_seat)
    expect_the_card(table)
    expect_the_page_around_the_card(table.everyone)
    expect_the_marks(table, set())
    expect_the_buttons(table, set())

    table.pages[first].locator(".actions").get_by_role("button", name=WEITER).click()
    expect_the_marks(table, {first})
    expect_the_buttons(table, {first})
    expect_the_bars_inside_the_pages(table)
    reload_everyone(table)
    expect_the_card(table)
    expect_the_marks(table, {first})
    expect_the_buttons(table, {first})

    table.pages[second].locator(".actions").get_by_role("button", name=WEITER).click()
    table.pages[table.declarer_seat].locator(".actions").get_by_role("button", name=WEITER).click()
    for person in table.everyone:
        expect(person.locator(CARD)).to_have_count(0)
    for person in table.pages.values():
        expect(person.locator(OWN_HAND_CARD)).to_have_count(CARDS_IN_A_HAND)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_very_long_name_leaves_every_pill_of_the_result_bar_whole(
    deal_a_finished_hand: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor, joiners=LONG_NAMES)
    person = table.pages[table.declarer_seat]
    bar = person.locator(".actions")
    bar.get_by_role("button", name=WEITER).click()
    expect(bar.get_by_role("status")).to_contain_text(awaited(table, {table.declarer_seat}))
    heights = bar.evaluate(PILL_HEIGHTS)
    link = bar.locator(".copy.link").bounding_box()
    assert link is not None
    assert link["width"] >= link["height"]
    assert len(set(heights)) == 1
    expect_the_bars_inside_the_pages(table)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_wait_pill_holds_its_whole_text_with_a_25_character_name(
    deal_a_finished_hand: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor, joiners=("Maximiliane-Bartholomaea1", "cleo"))
    bar = table.pages[table.declarer_seat].locator(".actions")
    bar.get_by_role("button", name=WEITER).click()
    pill = bar.get_by_role("status")
    expect(pill).to_be_visible()
    assert pill.evaluate(
        "pill => pill.scrollHeight <= pill.clientHeight + 1 && pill.scrollWidth <= pill.clientWidth + 1"
    )
    heights = bar.evaluate(PILL_HEIGHTS)
    assert len(set(heights)) == 1
    expect_the_bars_inside_the_pages(table)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_member_who_stands_up_leaves_a_free_chair_and_the_card_stays(
    deal_a_finished_hand: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor)
    leaver, other = (seat for seat in table.names if seat != table.declarer_seat)
    table.ready_through_the_api(leaver)
    expect_the_marks(table, {leaver})

    table.pages[leaver].locator(".actions").get_by_role("button", name=STAND_UP).click()

    for person in (table.pages[table.declarer_seat], table.pages[other], table.watcher):
        expect(person.locator(f".chair[data-seat='{leaver}'] .plate")).to_have_text(SEAT_FREE)
        expect(person.locator(f".chair[data-seat='{leaver}'] {READY_MARK}")).to_have_count(0)
        expect(person.locator(CARD)).to_have_count(1)
    expect(table.watcher.locator(f".chair[data-seat='{leaver}']").get_by_role("button", name=SIT_DOWN)).to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_tap_on_a_result_the_table_has_left_shows_the_failure_note(
    deal_a_finished_hand: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    # The browser logs the refused tap as a console error; that refusal is the point of this test.
    table = deal_a_finished_hand(form_factor, console=False)
    tapper_seat = next(seat for seat in table.names if seat != table.declarer_seat)
    tapper = table.pages[tapper_seat]

    def tap_for_another_result(route: Route) -> None:
        route.continue_(post_data='{"command_id": "stale-tap", "ordinal": 99}')

    tapper.route(f"**{table.declaring.api_path}{TABLE_READY_SUFFIX}", tap_for_another_result)
    tapper.locator(".actions").get_by_role("button", name=WEITER).click()

    expect(tapper.locator(".note")).to_have_text(COMMAND_FAILED)
    expect_the_marks(table, set())
    expect(tapper.locator(".actions").get_by_role("button", name=WEITER)).to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_next_hand_waits_for_an_away_member_who_tapped_until_they_are_back(
    deal_a_finished_hand: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor)
    away_seat, other_seat = (seat for seat in table.names if seat != table.declarer_seat)
    away = table.pages[away_seat]
    away.locator(".actions").get_by_role("button", name=WEITER).click()
    expect_the_marks(table, {away_seat})
    away.close()
    declarer, other = table.pages[table.declarer_seat], table.pages[other_seat]
    expect(declarer.locator(f".chair[data-seat='{away_seat}']")).to_contain_text(SEAT_AWAY)

    for person in (declarer, other):
        person.locator(".actions").get_by_role("button", name=WEITER).click()

    for person in (declarer, other):
        expect(person.locator(".actions").get_by_role("status")).to_have_text(f"{WAITING_FOR} {table.names[away_seat]}")
        expect(person.locator(CARD)).to_have_count(1)

    back = away.context.new_page()
    back.goto(declarer.url)
    for person in (declarer, other, table.watcher, back):
        expect(person.locator(CARD)).to_have_count(0)
    assert page_errors == []
