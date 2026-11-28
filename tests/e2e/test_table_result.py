from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from skat.engine.bidding import VALID_BIDS
from skat.engine.tricks import CARDS_IN_A_GAME
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface
from tests.e2e.support.declaring import AuctionCall, DeclaringTable, bids, passes
from tests.e2e.support.hands import THEY, WE, PlayingTable, deal_playing_table
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.result_card import (
    CARD,
    LOST,
    OVERBID,
    SERIES_GONE,
    TIMES,
    WAITING_FOR_PLAYERS,
    WON,
    YOU,
    expect_a_new_sitter_reads_the_leaver_as_gone,
    loosely,
    signed,
    waiting_for,
)
from tests.e2e.support.style import STYLE_KEY
from tests.e2e.support.table_menu import close_table_menu, menu_button
from tests.e2e.support.tables import SIT_DOWN, chair_of, plate_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

WEITER = text(SOURCE_LANGUAGE, "table.weiter")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
COPY_LINK = text(SOURCE_LANGUAGE, "table.copyLink")
COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
SEAT_AWAY = text(SOURCE_LANGUAGE, "table.seatAway")
SEAT_FREE = text(SOURCE_LANGUAGE, "table.seatFree")
PLAYS = text(SOURCE_LANGUAGE, "table.plays")
TAPPED_WEITER = text(SOURCE_LANGUAGE, "table.readyMark")
TRICK_POINTS = text(SOURCE_LANGUAGE, "result.trickPoints")
CARDS_IN_A_HAND = 10


class ModestBidTable(DeclaringTable):
    """The middlehand bids the lowest value, so the game declared lies above it and is never overbid."""

    auction: ClassVar[tuple[AuctionCall, ...]] = (
        bids("middlehand", VALID_BIDS[0]),
        passes("forehand"),
        passes("rearhand"),
    )


HANDS = [pytest.param(DeclaringTable, id="overbid"), pytest.param(ModestBidTable, id="modest")]


@pytest.fixture
def deal_a_finished_hand(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    def deal(
        form_factor: dict[str, Any], *, declaring: type[DeclaringTable] = DeclaringTable, console: bool = True
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
        )
        table.play_out(CARDS_IN_A_GAME)
        return table

    return deal


def awaited(table: PlayingTable, ready: set[int]) -> list[str]:
    return [name for seat, name in table.names.items() if seat not in ready]


def role_of(table: PlayingTable, person: Page) -> str:
    if person is table.watcher:
        return "watcher"
    return "declarer" if person is table.pages[table.declarer_seat] else "opponent"


def expected_word(table: PlayingTable, person: Page) -> str:
    won = table.result()["won"]
    role = role_of(table, person)
    if role == "watcher":
        return text(
            SOURCE_LANGUAGE,
            "result.declarerWins" if won else "result.declarerLoses",
            name=table.names[table.declarer_seat],
        )
    return WON if won == (role == "declarer") else LOST


def weiter_key(person: Page) -> Locator:
    return person.get_by_role("button", name=WEITER, exact=True)


def ready_mark(person: Page, seat: int) -> Locator:
    return chair_of(person, seat).get_by_title(TAPPED_WEITER, exact=True)


def expect_the_raise(person: Page, result: dict[str, Any]) -> None:
    card = person.locator(CARD)
    if result["overbid"]:
        expect(old_surface.result_stamp(person)).to_have_text(OVERBID)
        expect(card.locator(".miss:not(.missed)")).to_have_text(
            text(
                SOURCE_LANGUAGE,
                "result.raise",
                value=str(result["game_value"]),
                bid=str(result["bid"]),
                settled=str(result["settled_value"]),
            )
        )
    else:
        expect(old_surface.result_stamp(person)).to_have_count(0)
        expect(card.locator(".miss:not(.missed)")).to_have_count(0)


def expect_the_rows(table: PlayingTable, person: Page, role: str, result: dict[str, Any]) -> None:
    expect(old_surface.reckoning_tiles(person)).to_have_count(3)
    for gain in result["gains"]:
        row = person.locator(CARD).locator(f".reck[data-seat='{gain['seat']}']")
        expect(row.locator(".dl")).to_have_text(signed(gain["gain"]) if gain["gain"] else "0")
        own = role != "watcher" and person is table.pages[gain["seat"]]
        expect(old_surface.reckoning_name(person, gain["seat"])).to_have_text(YOU if own else table.names[gain["seat"]])


def expect_the_card(table: PlayingTable) -> None:
    """Every viewer reads the card as the answer counted it, from their own side."""
    result = table.result()
    for person in table.everyone:
        role = role_of(table, person)
        card = person.locator(CARD)
        expect(card).to_have_count(1)
        expect(card.get_by_role("heading")).to_have_text(expected_word(table, person))
        expect(card.locator(".value")).to_have_text(signed(result["score"]))
        expect(card.locator(".x2")).to_have_count(1 if result["doubled"] else 0)
        expect(card.get_by_role("listitem")).to_have_count(len(result["levels"]) + 1)
        equation = [str(result["multiplier"]), TIMES, str(result["base_value"])]
        if result["doubled"]:
            equation += ["=", str(result["game_value"])]
        expect(card.locator(".eq")).to_have_text(loosely(*equation))
        expect(card.locator(".miss.missed")).to_have_count(1 if result["announcement_missed"] else 0)
        expect_the_raise(person, result)
        names = {"declarer": (YOU, THEY), "opponent": (table.names[table.declarer_seat], WE)}.get(
            role, (table.names[table.declarer_seat], THEY)
        )
        points = card.get_by_role("group", name=TRICK_POINTS)
        for side, counted in zip(names, (result["declarer_points"], result["opponents_points"]), strict=True):
            expect(points).to_contain_text(text(SOURCE_LANGUAGE, "result.sidePoints", side=side, points=str(counted)))
        declarer_gain = next(gain for gain in result["gains"] if gain["seat"] == result["declarer_seat"])["gain"]
        opponent_gain = next(gain for gain in result["gains"] if gain["seat"] != result["declarer_seat"])["gain"]
        steps = [
            names[0],
            text(SOURCE_LANGUAGE, "result.listGame", score=signed(result["score"])),
            text(SOURCE_LANGUAGE, "result.listBonus", bonus=signed(result["list_bonus"])),
            f"= {signed(declarer_gain)}",
        ]
        if result["doubled"]:
            steps.append(text(SOURCE_LANGUAGE, "result.share", opponents=names[1], gain=signed(opponent_gain)))
        expect(card.locator(".list")).to_have_text(loosely(*steps))
        expect_the_rows(table, person, role, result)


def expect_the_marks(table: PlayingTable, ready: set[int]) -> None:
    for person in table.everyone:
        expect(old_surface.chairs(person).get_by_text(PLAYS, exact=True)).to_have_count(1)
        expect(chair_of(person, table.declarer_seat).get_by_text(PLAYS, exact=True)).to_have_count(1)
        for seat in table.names:
            expect(ready_mark(person, seat)).to_have_count(1 if seat in ready else 0)


def expect_the_buttons(table: PlayingTable, ready: set[int]) -> None:
    """The seated viewers find „Weiter“ until they have tapped, then who is awaited; the watcher finds neither.

    Standing up and the link lie behind the menu's key, which offers no style while the result stands; the watcher's
    menu offers no standing up.
    """
    for seat, person in table.pages.items():
        expect(person.get_by_role("button", name=STAND_UP, exact=True)).to_have_count(0)
        expect(person.get_by_role("button", name=COPY_LINK, exact=True)).to_have_count(0)
        expect(menu_button(person, STAND_UP)).to_be_visible()
        expect(menu_button(person, COPY_LINK)).to_be_visible()
        expect(menu_button(person, STYLE_KEY)).to_have_count(0)
        close_table_menu(person)
        if seat in ready:
            expect(weiter_key(person)).to_have_count(0)
            expect(person.get_by_text(waiting_for(awaited(table, ready)), exact=True)).to_be_visible()
        else:
            expect(weiter_key(person)).to_be_visible()
    expect(weiter_key(table.watcher)).to_have_count(0)
    expect(menu_button(table.watcher, STAND_UP)).to_have_count(0)
    close_table_menu(table.watcher)


def reload_everyone(table: PlayingTable) -> None:
    for person in table.everyone:
        person.reload()
        old_surface.expect_the_table_shown(person)


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
    for person in table.everyone:
        expect(old_surface.card_faces(person)).to_have_count(0)
        expect(person.get_by_text(WAITING_FOR_PLAYERS)).to_have_count(0)
    expect_the_marks(table, set())
    expect_the_buttons(table, set())

    weiter_key(table.pages[first]).click()
    expect_the_marks(table, {first})
    expect_the_buttons(table, {first})
    reload_everyone(table)
    expect_the_card(table)
    expect_the_marks(table, {first})
    expect_the_buttons(table, {first})

    weiter_key(table.pages[second]).click()
    weiter_key(table.pages[table.declarer_seat]).click()
    for person in table.everyone:
        expect(person.locator(CARD)).to_have_count(0)
    for person in table.pages.values():
        expect(old_surface.own_cards(person)).to_have_count(CARDS_IN_A_HAND)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_member_who_stands_up_leaves_a_free_chair_and_the_card_stays(
    deal_a_finished_hand: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor)
    leaver, other = (seat for seat in table.names if seat != table.declarer_seat)
    table.ready_through_the_api(leaver)
    expect_the_marks(table, {leaver})

    menu_button(table.pages[leaver], STAND_UP).click()

    for person in (table.pages[table.declarer_seat], table.pages[other], table.watcher):
        expect(plate_of(person, leaver)).to_have_text(SEAT_FREE)
        expect(ready_mark(person, leaver)).to_have_count(0)
        expect(person.locator(CARD)).to_have_count(1)
    expect(chair_of(table.watcher, leaver).get_by_role("button", name=SIT_DOWN)).to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_declarer_who_stands_up_stays_on_the_card_by_name_marked_gone(
    deal_a_finished_hand: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor)
    declarer = table.declarer_seat

    menu_button(table.pages[declarer], STAND_UP).click()

    for person in (*(page for seat, page in table.pages.items() if seat != declarer), table.watcher):
        expect(plate_of(person, declarer)).to_have_text(SEAT_FREE)
        expect(old_surface.reckoning_name(person, declarer)).to_contain_text(table.names[declarer])
        expect(old_surface.gone_note(person, declarer)).to_have_text(SERIES_GONE)
        expect(person.locator(CARD)).not_to_contain_text(SEAT_FREE)
    expect_a_new_sitter_reads_the_leaver_as_gone(table.watcher, declarer, table.names[declarer])
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_weiter_names_the_series_the_page_shows(
    deal_a_finished_hand: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor)
    tapper_seat = next(seat for seat in table.names if seat != table.declarer_seat)
    tapper = table.pages[tapper_seat]

    with tapper.expect_request(lambda request: request.url.endswith(TABLE_READY_SUFFIX)) as tap:
        weiter_key(tapper).click()

    assert tap.value.post_data_json["series"] == table.view(tapper_seat)["series"]["number"]
    expect_the_marks(table, {tapper_seat})


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_tap_on_a_result_the_table_has_left_shows_the_failure_note(
    deal_a_finished_hand: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    # The browser logs the refused tap as a console error; that refusal is the point of this test.
    table = deal_a_finished_hand(form_factor, console=False)
    tapper_seat = next(seat for seat in table.names if seat != table.declarer_seat)
    tapper = table.pages[tapper_seat]

    def tap_for_another_result(route: Route) -> None:
        route.continue_(post_data='{"command_id": "stale-tap", "ordinal": 99, "series": 1}')

    tapper.route(f"**{table.declaring.api_path}{TABLE_READY_SUFFIX}", tap_for_another_result)
    weiter_key(tapper).click()

    expect(old_surface.note(tapper)).to_have_text(COMMAND_FAILED)
    expect_the_marks(table, set())
    expect(weiter_key(tapper)).to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_next_hand_waits_for_an_away_member_who_tapped_until_they_are_back(
    deal_a_finished_hand: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor)
    away_seat, other_seat = (seat for seat in table.names if seat != table.declarer_seat)
    away = table.pages[away_seat]
    weiter_key(away).click()
    expect_the_marks(table, {away_seat})
    away.close()
    declarer, other = table.pages[table.declarer_seat], table.pages[other_seat]
    expect(chair_of(declarer, away_seat)).to_contain_text(SEAT_AWAY)

    for person in (declarer, other):
        weiter_key(person).click()

    for person in (declarer, other):
        expect(person.get_by_text(waiting_for([table.names[away_seat]]), exact=True)).to_be_visible()
        expect(person.locator(CARD)).to_have_count(1)

    back = away.context.new_page()
    back.goto(declarer.url)
    for person in (declarer, other, table.watcher, back):
        expect(person.locator(CARD)).to_have_count(0)
    assert page_errors == []
