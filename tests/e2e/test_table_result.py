from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from skat.engine.bidding import VALID_BIDS
from skat.engine.tricks import CARDS_IN_A_GAME
from skat.table.records import TableStyle
from skat.web.calling import AGENT_ADDERS_GROUP
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import (
    DEFAULT_JOINERS,
    DEFAULT_OPENER,
    TAKE_SKAT,
    AuctionCall,
    DeclaringTable,
    bids,
    button_of,
    passes,
)
from tests.e2e.support.hands import INSIDE_THE_VISIBLE_STRIP, THEY, WE, PlayingTable, deal_playing_table
from tests.e2e.support.motion import FELT_SLOT, names_under_something
from tests.e2e.support.people import DESKTOP, WIDTHS
from tests.e2e.support.result_card import (
    CARD,
    LOST,
    OVERBID,
    TIMES,
    WON,
    YOU,
    expect_the_page_around_the_card,
    expect_the_seat_tiles_inside_the_card,
    loosely,
    signed,
    waiting_for,
)
from tests.e2e.support.style import (
    STYLES,
    TABLE_SCENES,
    expect_painted_as_the_scene,
    expect_the_furniture_clear,
    give_the_table_its_style,
)
from tests.e2e.support.table_menu import AGENTS_PANEL, close_table_menu, menu_button, open_agents_panel
from tests.e2e.support.tables import SIT_DOWN

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

SEAT_TILE_PAINT = ["backgroundImage", "backgroundColor", "color", "boxShadow"]
WEITER = text(SOURCE_LANGUAGE, "table.weiter")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
COPY_LINK = text(SOURCE_LANGUAGE, "table.copyLink")
COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
SEAT_AWAY = text(SOURCE_LANGUAGE, "table.seatAway")
SEAT_FREE = text(SOURCE_LANGUAGE, "table.seatFree")
READY_MARK = ".mark.ready"
OWN_HAND_CARD = ".own-hand .card"
CARDS_IN_A_HAND = 10
LONG_NAMES = ("Bartholom\u00e4us-Maximilian-Ferdinand", "Maximiliane-Bartholom\u00e4a-Ferdinande")
# Three 25-character account names: the seat that opens a table and the two that join it.
FULL_LENGTH_OPENER = "Maximiliane-Bartholomaea0"
FULL_LENGTH_NAMES = ("Maximiliane-Bartholomaea1", "Maximiliane-Bartholomaea2")
ORDINARY_NAMES = ("Felix", "Nova")
PICKED_INDEX = 7

# The agents' list keeps this far from either edge of the screen, in pixels.
EDGE_MARGIN = 16
FRAMES_AFTER_THE_CARD = 90
# Every frame from now on, the open list's distance to each edge of the screen the person's device has (not of the
# layout width a widened page reports); after the card stands, `framesAfterTheCard` counts the frames.
WATCH_THE_OPEN_LIST = """
    ([screenWidth, margin, menu]) => {
        window.listOutside = [];
        window.framesAfterTheCard = 0;
        const watch = () => {
            const list = document.querySelector(menu)?.getBoundingClientRect();
            if (list !== undefined && (list.left < margin - 0.5 || list.right > screenWidth - margin + 0.5)) {
                window.listOutside.push([list.left, list.right, innerWidth]);
            }
            if (document.querySelector(".result") !== null) window.framesAfterTheCard += 1;
            requestAnimationFrame(watch);
        };
        requestAnimationFrame(watch);
    }
"""

PILL_HEIGHTS = "bar => [...bar.children].map(child => child.getBoundingClientRect().height)"


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
    table_style: TableStyle,
) -> Callable[..., PlayingTable]:
    def deal(
        form_factor: dict[str, Any],
        *,
        declaring: type[DeclaringTable] = DeclaringTable,
        console: bool = True,
        joiners: tuple[str, str] = DEFAULT_JOINERS,
        opener_name: str = DEFAULT_OPENER,
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
            opener_name=opener_name,
        )
        give_the_table_its_style(table.pages[table.seat_at["forehand"]], table.everyone, table_style)
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


def expect_the_raise(card: Locator, result: dict[str, Any]) -> None:
    if result["overbid"]:
        expect(card.locator(".stamp")).to_have_text(OVERBID)
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
        expect(card.locator(".sides .declarer")).to_have_text(
            text(SOURCE_LANGUAGE, "result.sidePoints", side=names[0], points=str(result["declarer_points"]))
        )
        expect(card.locator(".sides .opponents")).to_have_text(
            text(SOURCE_LANGUAGE, "result.sidePoints", side=names[1], points=str(result["opponents_points"]))
        )
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
    """The seated viewers' bars: „Weiter“ until they have tapped, then who is awaited; the watcher's has neither.

    Standing up and the link lie in the menu, not in the bar.
    """
    for seat, person in table.pages.items():
        bar = person.locator(".actions")
        assert bar.evaluate("bar => new Set([...bar.children].map(child => child.offsetTop)).size") == 1
        expect(bar.get_by_role("button", name=STAND_UP)).to_have_count(0)
        expect(bar.get_by_role("button", name=COPY_LINK)).to_have_count(0)
        expect(menu_button(person, STAND_UP)).to_be_visible()
        expect(menu_button(person, COPY_LINK)).to_be_visible()
        close_table_menu(person)
        if seat in ready:
            expect(bar.get_by_role("button", name=WEITER)).to_have_count(0)
            expect(bar.get_by_role("status")).to_have_text(waiting_for(awaited(table, ready)))
        else:
            expect(bar.get_by_role("button", name=WEITER)).to_be_visible()
    expect(table.watcher.locator(".actions").get_by_role("button", name=WEITER)).to_have_count(0)
    expect(table.watcher.locator(".row.stand")).to_have_count(0)


def reload_everyone(table: PlayingTable) -> None:
    for person in table.everyone:
        person.reload()
        expect(person.locator(".chair")).to_have_count(3)


@pytest.mark.parametrize("table_style", STYLES)
@pytest.mark.parametrize("declaring", HANDS)
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_everyone_reads_the_result_and_the_three_taps_deal_the_next_hand(
    deal_a_finished_hand: Callable[..., PlayingTable],
    page_errors: list[str],
    form_factor: dict[str, Any],
    declaring: type[DeclaringTable],
    table_style: TableStyle,
) -> None:
    table = deal_a_finished_hand(form_factor, declaring=declaring)
    first, second = (seat for seat in table.names if seat != table.declarer_seat)
    expect_the_card(table)
    expect_the_seat_tiles_inside_the_card(table.everyone)
    expect_the_page_around_the_card(table.everyone)
    expect_the_furniture_clear(table.everyone, table_style)
    if table_style is TableStyle.STRANDBAR:
        for person in table.everyone:
            expect_painted_as_the_scene(
                person, "strand-result", ".result .reck:not(.win)", ".reck:not(.win)", SEAT_TILE_PAINT
            )
    for person in table.everyone:
        expect(person.locator(".row.style")).to_have_count(0)
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


@pytest.mark.usefixtures("realm_reusing_refresh_tokens")
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_result_bar_stays_inside_the_page_with_the_agents_in_the_menu(
    deal_a_finished_hand: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand({**form_factor, "groups": (AGENT_ADDERS_GROUP,)})
    for person in table.everyone:
        open_agents_panel(person)
        close_table_menu(person)
    expect_the_bars_inside_the_pages(table)


@pytest.mark.usefixtures("realm_reusing_refresh_tokens")
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_list_left_open_stays_inside_the_margin_as_the_result_slides_in_and_the_bar_keeps_clear(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(
        open_person, e2e_server, member_of, page_errors, {**form_factor, "groups": (AGENT_ADDERS_GROUP,)}
    )
    person = table.pages[table.declarer_seat]
    open_agents_panel(person)
    person.evaluate(WATCH_THE_OPEN_LIST, [form_factor["viewport"]["width"], EDGE_MARGIN, AGENTS_PANEL])

    table.play_out(CARDS_IN_A_GAME)
    expect(person.locator(CARD)).to_have_count(1)
    person.wait_for_function("frames => window.framesAfterTheCard >= frames", arg=FRAMES_AFTER_THE_CARD)

    assert person.evaluate("window.listOutside") == []
    expect(person.locator(".agents-list")).to_be_visible()
    bar = person.locator(".actions").bounding_box()
    card = person.locator(CARD).bounding_box()
    assert bar is not None
    assert card is not None
    assert bar["y"] >= card["y"] + card["height"]
    assert person.locator(OWN_HAND_CARD).count() == 0 or bar["y"] >= max(
        box["y"] + box["height"] for box in map(Locator.bounding_box, person.locator(OWN_HAND_CARD).all()) if box
    )


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_very_long_name_leaves_every_pill_of_the_result_bar_whole(
    deal_a_finished_hand: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor, joiners=LONG_NAMES)
    person = table.pages[table.declarer_seat]
    bar = person.locator(".actions")
    bar.get_by_role("button", name=WEITER).click()
    expect(bar.get_by_role("status")).to_contain_text(waiting_for(awaited(table, {table.declarer_seat})))
    assert len(set(bar.evaluate(PILL_HEIGHTS))) == 1
    expect_the_bars_inside_the_pages(table)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_wait_pill_stays_as_tall_as_the_weiter_key_with_two_25_character_names(
    deal_a_finished_hand: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor, joiners=FULL_LENGTH_NAMES, opener_name=FULL_LENGTH_OPENER)
    bar = table.pages[table.declarer_seat].locator(".actions")
    weiter = bar.get_by_role("button", name=WEITER)
    weiter_box = weiter.bounding_box()
    assert weiter_box is not None
    weiter.click()
    pill = bar.get_by_role("status")
    expect(pill).to_be_visible()
    assert max(bar.evaluate(PILL_HEIGHTS)) <= weiter_box["height"] + 1
    expect_the_bars_inside_the_pages(table)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_stand_up_row_keeps_its_word_while_the_bar_waits(
    deal_a_finished_hand: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor)
    person = next(iter(table.pages.values()))
    bar = person.locator(".actions")
    bar.get_by_role("button", name=WEITER).click()
    expect(bar.get_by_role("status")).to_be_visible()
    label = menu_button(person, STAND_UP).locator(".label")
    assert label.evaluate("label => Math.ceil(label.getBoundingClientRect().width) >= label.scrollWidth")


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
        expect(person.locator(f".chair[data-seat='{leaver}'] .plate")).to_have_text(SEAT_FREE)
        expect(person.locator(f".chair[data-seat='{leaver}'] {READY_MARK}")).to_have_count(0)
        expect(person.locator(CARD)).to_have_count(1)
    expect(table.watcher.locator(f".chair[data-seat='{leaver}']").get_by_role("button", name=SIT_DOWN)).to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_weiter_names_the_series_the_page_shows(
    deal_a_finished_hand: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor)
    tapper_seat = next(seat for seat in table.names if seat != table.declarer_seat)
    tapper = table.pages[tapper_seat]

    with tapper.expect_request(lambda request: request.url.endswith(TABLE_READY_SUFFIX)) as tap:
        tapper.locator(".actions").get_by_role("button", name=WEITER).click()

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
        expect(person.locator(".actions").get_by_role("status")).to_have_text(waiting_for([table.names[away_seat]]))
        expect(person.locator(CARD)).to_have_count(1)

    back = away.context.new_page()
    back.goto(declarer.url)
    for person in (declarer, other, table.watcher, back):
        expect(person.locator(CARD)).to_have_count(0)
    assert page_errors == []


# The pairs of elements whose boxes lie more than a pixel across each other, each named by its selector and chair.
CROSSINGS = """([firsts, seconds]) => {
    const name = (element) => {
        const chair = element.closest('.chair');
        return `${chair ? `chair ${chair.dataset.seat} ` : ''}${element.className}`;
    };
    const crossing = (a, b) =>
        Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
        Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;
    const found = [];
    for (const first of document.querySelectorAll(firsts)) {
        for (const second of document.querySelectorAll(seconds)) {
            if (first.contains(second) || second.contains(first)) continue;
            if (crossing(first.getBoundingClientRect(), second.getBoundingClientRect())) {
                found.push(`${name(first)} over ${name(second)}`);
            }
        }
    }
    return found;
}"""


def expect_no_crossing(person: Page, firsts: str, seconds: str) -> None:
    assert person.evaluate(CROSSINGS, [firsts, seconds]) == []


@pytest.fixture
def deal_a_table_of_full_length_names(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., DeclaringTable]:
    def deal(form_factor: dict[str, Any]) -> DeclaringTable:
        return DeclaringTable(open_person, e2e_server, member_of, page_errors, form_factor, joiners=FULL_LENGTH_NAMES)

    return deal


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_laid_name_tags_of_full_length_names_stay_clear_of_each_other_and_of_the_other_slots_above_every_card(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(
        open_person,
        e2e_server,
        member_of,
        page_errors,
        form_factor,
        joiners=FULL_LENGTH_NAMES,
        opener_name=FULL_LENGTH_OPENER,
    )
    table.leave_the_last_trick_on_the_felt()
    for plays, laid in ((2, 2), (1, 3)):
        table.play_out(plays)
        for person in table.everyone:
            expect(person.locator(".trick .laid")).to_have_count(laid)
            expect_no_crossing(person, ".trick .laid .tag", ".trick .laid .tag")
            expect_no_crossing(person, ".trick .laid .tag", FELT_SLOT)
            assert names_under_something(person) == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_laid_name_tags_of_ordinary_names_show_each_name_whole(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, joiners=ORDINARY_NAMES)
    table.leave_the_last_trick_on_the_felt()
    table.play_out(3)
    for person in table.everyone:
        expect(person.locator(".trick .laid")).to_have_count(3)
        clipped = person.locator(".trick .laid .name").evaluate_all(
            "names => names.filter(name => name.scrollWidth > name.clientWidth).map(name => name.textContent)"
        )
        assert clipped == []
        # Each tag hangs below its own card by the same distance, so no tag steps below the others.
        drops = person.locator(".trick .laid").evaluate_all(
            "cards => cards.map(card => { const tag = card.querySelector('.tag');"
            " return tag.offsetTop + tag.offsetHeight - card.offsetHeight; })"
        )
        assert len(set(drops)) == 1


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_card_counts_of_full_length_names_stand_clear_of_the_plates(
    deal_a_table_of_full_length_names: Callable[..., DeclaringTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_table_of_full_length_names(form_factor)
    for person in (table.declarer, *table.others, table.watcher):
        expect(person.locator(".plate")).to_have_count(3)
        expect_no_crossing(person, ".count-tag", ".plate")


def test_the_coasters_of_the_far_chairs_stand_clear_of_full_length_names_on_a_desktop(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = deal_playing_table(
        open_person,
        e2e_server,
        member_of,
        page_errors,
        DESKTOP,
        joiners=FULL_LENGTH_NAMES,
        opener_name=FULL_LENGTH_OPENER,
    )
    table.play_out(CARDS_IN_A_GAME)
    for person in table.everyone:
        expect(person.locator(".chair .coaster")).to_have_count(3)
        expect_no_crossing(person, ".chair .coaster", ".chair .plate")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_dealers_pass_mark_stands_clear_of_the_position_label(
    deal_a_table_of_full_length_names: Callable[..., DeclaringTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_table_of_full_length_names(form_factor)
    for person in (table.declarer, *table.others, table.watcher):
        expect(person.locator(".mark.pass").first).to_be_visible()
        expect_no_crossing(person, ".mark.pass", ".mark.pos")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_away_note_of_the_near_chair_stands_clear_of_the_bar(
    deal_a_table_of_full_length_names: Callable[..., DeclaringTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_table_of_full_length_names(form_factor)
    near_seat = max(chair["seat"] for chair in table.chairs())
    next(person for person in (table.declarer, *table.others) if PlayingTable.seat_of(person) == near_seat).close()
    expect(table.watcher.locator(f".chair[data-seat='{near_seat}'] .mark.away")).to_have_count(1)
    expect_no_crossing(table.watcher, ".chair .plate small", ".actions")


@pytest.mark.parametrize("position", ["forehand", "middlehand", "rearhand"])
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_away_mark_stands_clear_of_the_position_label_in_play(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
    position: str,
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, joiners=FULL_LENGTH_NAMES)
    seat = table.seat_at[position]
    table.pages[seat].close()
    expect(table.watcher.locator(f".chair[data-seat='{seat}'] .mark.away")).to_have_count(1)
    expect_no_crossing(table.watcher, ".mark.away", ".mark.pos")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_picked_card_lifts_clear_of_the_near_chair_and_the_bar_stays_on_the_screen(
    deal_a_table_of_full_length_names: Callable[..., DeclaringTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_table_of_full_length_names(form_factor)
    declarer = table.declarer
    button_of(declarer, TAKE_SKAT).click()
    expect(declarer.locator(".own-hand .pick")).to_have_count(CARDS_IN_A_HAND + 2)
    declarer.locator(".own-hand .pick").nth(PICKED_INDEX).click(position=INSIDE_THE_VISIBLE_STRIP)
    expect(declarer.locator(".own-hand .pick.picked")).to_have_count(1)
    expect_no_crossing(declarer, ".own-hand .pick.picked", ".chair.mine .tile")
    expect_no_crossing(declarer, ".own-hand .pick.picked", ".chair.mine .plate")
    bar = declarer.locator(".actions").bounding_box()
    assert bar is not None
    assert bar["y"] + bar["height"] <= declarer.evaluate("window.innerHeight")


# On a desktop the own seat is a slim bar centred over the hand, never a tile of the felt's size, so no card the finger
# holds up, no trick card or tag lies under it.
OWN_BAR_HEIGHT = 56
# Where the dashed slot stands before the viewer's card lies, and the card once it lies, there.
TRICK_THINGS = ".trick .face, .trick .tag, .trick .lead-slot"
# The bar's own ring marks the turn, so the avatar in it carries no ring, no stool stands under the bar and the name
# is plain text on it, with no plate of its own.
OWN_BAR_ON_TURN = """() => {
    const chair = document.querySelector('.chair.mine');
    const tile = getComputedStyle(chair.querySelector('.tile'));
    const plate = getComputedStyle(chair.querySelector('.plate'));
    const stool = getComputedStyle(chair, '::after');
    return {
        avatarRing: tile.boxShadow,
        plateRing: plate.boxShadow,
        plateBackground: plate.backgroundImage,
        stool: stool.display !== 'none' && stool.content !== 'none',
    };
}"""
LIFT_ONLY_THE_CARD_AT = """(index) => {
    const cards = [...document.querySelectorAll('.own-hand .card')];
    cards.forEach((card, at) => card.classList.toggle('touch', at === index));
}"""


@pytest.mark.parametrize("table_style", STYLES)
def test_the_own_seat_is_a_slim_bar_centred_over_the_hand_and_a_lifted_card_stands_clear_of_it_on_a_desktop(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    table_style: TableStyle,
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, DESKTOP, joiners=FULL_LENGTH_NAMES)
    give_the_table_its_style(table.pages[table.declarer_seat], table.everyone, table_style)
    table.play_through_the_api(sorted(table.legal_cards(table.seat_at["forehand"]))[0])
    middlehand = table.pages[table.seat_at["middlehand"]]
    legal_cards = middlehand.locator(f"{OWN_HAND_CARD}.ok")
    expect(legal_cards).to_have_count(len(table.legal_cards(table.seat_at["middlehand"])))

    bar = middlehand.locator(".chair.mine").bounding_box()
    assert bar is not None
    assert bar["height"] <= OWN_BAR_HEIGHT, "the own seat is a tile of the felt"
    assert abs(bar["x"] + bar["width"] / 2 - middlehand.evaluate("window.innerWidth / 2")) <= 1
    expect(middlehand.locator(".chair.mine.turn")).to_have_count(1)
    assert middlehand.evaluate(OWN_BAR_ON_TURN) == {
        "avatarRing": "none",
        "plateRing": "none",
        "plateBackground": "none",
        "stool": False,
    }
    for index in range(CARDS_IN_A_HAND):
        middlehand.evaluate(LIFT_ONLY_THE_CARD_AT, index)
        expect_no_crossing(middlehand, f"{OWN_HAND_CARD}.touch", ".chair.mine")
    legal_cards.first.locator("button").click(position=INSIDE_THE_VISIBLE_STRIP)
    expect(middlehand.locator(f"{OWN_HAND_CARD}.touch .swipe")).to_have_count(1)
    expect_no_crossing(middlehand, f"{OWN_HAND_CARD}:is(.ok, .touch), .own-hand .swipe", ".chair.mine")
    expect_no_crossing(middlehand, TRICK_THINGS, ".chair.mine")
    table.play_through_the_api(sorted(table.legal_cards(table.seat_at["middlehand"]))[0])
    expect(middlehand.locator(".trick .laid.near")).to_have_count(1)
    expect(middlehand.locator(".trick .lead-slot")).to_have_count(0)
    expect_no_crossing(middlehand, TRICK_THINGS, ".chair.mine")


# Each desktop scene's own seat, found by its class, against everything else the scene draws, except the cards sweeping
# to it and the list of games laid over the whole table.
OWN_SEATS_OF_THE_SCENES = """(maxHeight) => {
    const apart = [];
    const crossings = [];
    const crossing = (a, b) =>
        Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
        Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;
    for (const frame of document.querySelectorAll('.frame.d1280')) {
        const origin = frame.getBoundingClientRect();
        const own = [...frame.querySelectorAll('.seat.own')].filter((seat) => !seat.closest('.watchers'));
        if (frame.querySelector('.hand') && own.length === 0) apart.push(`${frame.id}: a hand and no own seat`);
        for (const seat of own) {
            const box = seat.getBoundingClientRect();
            if (!seat.classList.contains('bar') || box.height > maxHeight) {
                apart.push(`${frame.id}: the own seat is a tile`);
            }
            if (Math.abs(box.left + box.width / 2 - origin.left - origin.width / 2) > 1) {
                apart.push(`${frame.id}: off centre`);
            }
            for (const thing of frame.querySelectorAll(
                '.hand .card, .swipe, .play, .tag, .ghost, .plaque, .lastshow, .fan, .bubble, .notice, .result, '
                + '.coaster, .pile, .stamp'
            )) {
                if (seat.contains(thing) || thing.matches('.sweep, .gamelist')) continue;
                if (crossing(box, thing.getBoundingClientRect())) {
                    crossings.push(`${frame.id}: the own seat over ${thing.className}`);
                }
            }
        }
    }
    return { apart, crossings };
}"""


def test_every_desktop_scene_draws_the_own_seat_as_a_slim_bar_that_overlaps_nothing(page: Page) -> None:
    page.goto(TABLE_SCENES.as_uri())
    assert page.evaluate(OWN_SEATS_OF_THE_SCENES, OWN_BAR_HEIGHT) == {"apart": [], "crossings": []}
