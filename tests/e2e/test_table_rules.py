import json
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.web.playing import TABLE_GIVE_UP_SUFFIX
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import DESKTOP, WIDTHS
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.tables import open_new_table, watch

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

CHIPS = text(SOURCE_LANGUAGE, "rules.button")
CLOSE = text(SOURCE_LANGUAGE, "rules.close")
OFFICIAL = text(SOURCE_LANGUAGE, "rules.chipOfficial")
WE = text(SOURCE_LANGUAGE, "play.sideUs")
THEY = text(SOURCE_LANGUAGE, "play.sideThem")
YOU = text(SOURCE_LANGUAGE, "result.sideYou")
OPPONENTS = text(SOURCE_LANGUAGE, "result.sideThem")
CARDS_IN_A_TRICK = 3
CARDS_AFTER_TWO_TRICKS = 6
SHOWN_POINTS = ".plaque .points"

RUNNING_POINTS_ONLY = {"show_running_points": True}
KONTRA_AND_BOCK = {
    "show_running_points": True,
    "kontra": {"sayer": "bidders-only", "reach": "up-to-hirsch", "deadline": "own-card"},
    "bock": {"triggers": ["sixty-sixty", "schneider", "schwarz"], "overlap": "append"},
}
EVERY_RULE = {
    "kontra": {"sayer": "bidders-only", "reach": "up-to-hirsch", "deadline": "own-card"},
    "ramsch": {
        "occasion": "passed-in",
        "scoring": "points",
        "jungfrau": "doubles-loser",
        "durchmarsch": "wins-120",
        "pushing": {"rule": "jacks-stay"},
    },
    "bock": {
        "triggers": [
            "sixty-sixty",
            "won-grand-hand",
            "lost-after-kontra",
            "re",
            "passed-in",
            "schneider",
            "schwarz",
            "total-ending-in-00",
        ],
        "overlap": "append",
    },
}


def word(key: Any, **gaps: str) -> str:
    return text(SOURCE_LANGUAGE, key, **gaps)


def open_through_the_api(
    server: RunningServer, opener: SeededMember, options: dict[str, object] | None, command_id: str
) -> str:
    """The path of a table an agent or a script opened with these options."""
    body: dict[str, object] = {"command_id": command_id, "series_length": 30}
    if options is not None:
        body["options"] = options
    answer = json.loads(RawSession(server, opener).post(TABLES_PATH, body))
    return f"/t/{answer['id']}"


@pytest.fixture
def looks_at(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    e2e_server: RunningServer,
    page_errors: list[str],
) -> Callable[[dict[str, Any], dict[str, object] | None], Page]:
    """A signed-in person who looks at a table a member opened through the API with these options."""

    def look(form_factor: dict[str, Any], options: dict[str, object] | None) -> Page:
        opener = open_person(username="anna", **DESKTOP)
        path = open_through_the_api(e2e_server, member_of(opener), options, str(uuid.uuid4()))
        person = record_page_errors(open_person(username="dora", **form_factor), page_errors)
        watch(person, e2e_server, path)
        return person

    return look


def chips_of(person: Page) -> Locator:
    return person.get_by_role("button", name=CHIPS)


def sheet_of(person: Page) -> Locator:
    return person.locator("dialog.rules-sheet")


def assert_inside_the_screen(sheet: Locator, form_factor: dict[str, Any]) -> None:
    box = sheet.bounding_box()
    assert box is not None
    assert box["y"] >= 0
    assert box["y"] + box["height"] <= form_factor["viewport"]["height"]


def assert_apart(person: Page, *selectors: str) -> None:
    boxes = [person.locator(selector).bounding_box() for selector in selectors]
    for index, first in enumerate(boxes):
        assert first is not None
        for second in boxes[index + 1 :]:
            assert second is not None
            apart = (
                first["x"] + first["width"] <= second["x"]
                or second["x"] + second["width"] <= first["x"]
                or first["y"] + first["height"] <= second["y"]
                or second["y"] + second["height"] <= first["y"]
            )
            assert apart, (first, second)
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_watcher_sees_the_chips_of_a_table_opened_with_options_and_nothing_overlaps(
    looks_at: Callable[..., Page], form_factor: dict[str, Any]
) -> None:
    person = looks_at(form_factor, KONTRA_AND_BOCK)

    expect(chips_of(person).locator(".chip")).to_have_text(
        [word("rules.chipPoints"), word("rules.chipKontra"), word("rules.chipBock")]
    )
    assert_apart(person, ".lobby", ".sound-button", ".rulepill", ".watchers")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_every_chip_of_a_table_with_every_rule_fits_the_row(
    looks_at: Callable[..., Page], form_factor: dict[str, Any]
) -> None:
    person = looks_at(form_factor, {"show_running_points": True, **EVERY_RULE})

    expect(chips_of(person).locator(".chip")).to_have_text(
        [word("rules.chipPoints"), word("rules.chipKontra"), word("rules.chipRamsch"), word("rules.chipBock")]
    )
    assert_apart(person, ".lobby", ".sound-button", ".rulepill", ".watchers")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_table_without_options_shows_the_chip_official_and_no_rows(
    looks_at: Callable[..., Page], form_factor: dict[str, Any]
) -> None:
    person = looks_at(form_factor, None)

    expect(chips_of(person).locator(".chip")).to_have_text([OFFICIAL])
    chips_of(person).click()
    expect(sheet_of(person)).to_be_visible()
    expect(sheet_of(person).locator(".lockbadge")).to_contain_text(word("rules.lockBadge"))
    expect(sheet_of(person).locator(".rrow")).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_sheet_lists_a_row_per_rule_and_closes_by_its_button_and_by_escape_with_the_focus_back_on_the_chips(
    looks_at: Callable[..., Page], form_factor: dict[str, Any]
) -> None:
    person = looks_at(form_factor, KONTRA_AND_BOCK)
    sheet = sheet_of(person)

    chips_of(person).click()

    expect(sheet).to_be_visible()
    expect(sheet.locator(".rrow b")).to_have_text(
        [word("rules.namePoints"), word("rules.nameKontra"), word("rules.nameBock")]
    )
    expect(sheet.locator(".rrow").nth(1).locator("small span")).to_have_text(
        [
            word("rules.kontraSayerBiddersOnly"),
            word("rules.kontraReachUpToHirsch"),
            word("rules.kontraDeadlineOwnCard"),
        ]
    )
    expect(sheet.get_by_role("button", name=word("rules.info"))).to_be_visible()
    assert_inside_the_screen(sheet, form_factor)
    sheet.get_by_role("button", name=word("rules.info")).click()
    expect(sheet.get_by_text(word("rules.lockInfo"))).to_be_visible()
    sheet.get_by_role("button", name=CLOSE).click()
    expect(sheet).to_be_hidden()
    expect(chips_of(person)).to_be_focused()
    chips_of(person).click()
    expect(sheet).to_be_visible()
    person.keyboard.press("Escape")
    expect(sheet).to_be_hidden()
    expect(chips_of(person)).to_be_focused()


def test_the_chips_are_reached_by_tab_and_opened_by_enter(looks_at: Callable[..., Page]) -> None:
    person = looks_at(DESKTOP, RUNNING_POINTS_ONLY)

    for _ in range(5):
        person.keyboard.press("Tab")
        if person.evaluate("document.activeElement?.classList.contains('rulepill')"):
            break
    person.keyboard.press("Enter")

    expect(sheet_of(person)).to_be_visible()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_table_opened_with_every_rule_reads_all_its_rows(
    looks_at: Callable[..., Page], form_factor: dict[str, Any]
) -> None:
    person = looks_at(form_factor, EVERY_RULE)
    sheet = sheet_of(person)

    chips_of(person).click()

    expect(sheet.locator(".rrow b")).to_have_text(
        [word("rules.nameKontra"), word("rules.nameRamsch"), word("rules.namePushing"), word("rules.nameBock")]
    )
    expect(sheet.locator(".rrow").nth(1).locator("small span")).to_have_text(
        [
            word("rules.ramschScoringPoints"),
            word("rules.jungfrauDoublesLoser"),
            word("rules.durchmarschWins120"),
        ]
    )
    expect(sheet.locator(".rrow").nth(2).locator("small span")).to_have_text([word("rules.pushingJacksStay")])
    bock = sheet.locator(".rrow").nth(3).locator("small span")
    expect(bock).to_have_count(2)
    expect(bock.nth(1)).to_have_text(word("rules.bockOverlapAppend"))
    for trigger in (
        "SixtySixty",
        "WonGrandHand",
        "LostAfterKontra",
        "Re",
        "PassedIn",
        "Schneider",
        "Schwarz",
        "TotalEndingIn00",
    ):
        expect(bock.nth(0)).to_contain_text(word(f"rules.bockTrigger{trigger}"))
    assert_inside_the_screen(sheet, form_factor)


def sides_as_seen_by(table: PlayingTable, person: Page) -> tuple[str, str]:
    declarer = table.names[table.declarer_seat]
    if person is table.watcher:
        return declarer, THEY
    if person is table.pages[table.declarer_seat]:
        return YOU, OPPONENTS
    return declarer, WE


def expect_the_bar(table: PlayingTable, declarer_points: int, opponents_points: int) -> None:
    for person in table.everyone:
        declarer_side, opponents_side = sides_as_seen_by(table, person)
        bar = person.locator(SHOWN_POINTS)
        expect(bar.locator(".sides .declarer")).to_have_text(
            word("result.sidePoints", side=declarer_side, points=str(declarer_points))
        )
        expect(bar.locator(".sides .opponents")).to_have_text(
            word("result.sidePoints", side=opponents_side, points=str(opponents_points))
        )
        expect(bar.locator(".win-line")).to_be_visible()


@pytest.fixture
def deal_with_running_points(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    def deal(form_factor: dict[str, Any], game: str = "kreuz") -> PlayingTable:
        return deal_playing_table(
            open_person, e2e_server, member_of, page_errors, form_factor, game=game, running_points=True
        )

    return deal


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_plaque_counts_from_completed_tricks_for_the_players_and_a_watcher(
    deal_with_running_points: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_with_running_points(form_factor)

    expect_the_bar(table, 0, 0)
    for person in table.everyone:
        expect(chips_of(person).locator(".chip")).to_have_text([word("rules.chipPoints")])
    table.play_out(CARDS_IN_A_TRICK - 1)
    expect_the_bar(table, 0, 0)
    table.play_out(1)

    counted = table.playing()["running_points"]
    expect_the_bar(table, counted["declarer"], counted["opponents"])
    for person in table.everyone:
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_the_bar_stays_beside_a_standing_give_up_request(
    deal_with_running_points: Callable[..., PlayingTable],
) -> None:
    table = deal_with_running_points(DESKTOP)
    table.play_out(CARDS_AFTER_TWO_TRICKS)
    counted = table.playing()["running_points"]

    table.declaring.step(table.declarer_seat, TABLE_GIVE_UP_SUFFIX)

    for person in table.everyone:
        expect(person.locator(".plaque.ask")).to_be_visible()
    expect_the_bar(table, counted["declarer"], counted["opponents"])


def test_a_null_game_shows_no_bar(deal_with_running_points: Callable[..., PlayingTable]) -> None:
    table = deal_with_running_points(DESKTOP, "null")

    for person in table.everyone:
        expect(person.locator(".plaque")).to_be_visible()
        expect(person.locator(SHOWN_POINTS)).to_have_count(0)


def test_a_table_opened_without_the_switch_shows_no_bar(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)

    open_new_table(person, e2e_server)

    expect(chips_of(person).locator(".chip")).to_have_text([OFFICIAL])
    expect(person.locator(SHOWN_POINTS)).to_have_count(0)
