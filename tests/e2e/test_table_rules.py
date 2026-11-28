import json
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.web.playing import TABLE_GIVE_UP_SUFFIX
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import DESKTOP, WIDTHS
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.result_card import loosely
from tests.e2e.support.table_menu import menu_button
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
            "total-ending-in-00",
            "schwarz",
            "schneider",
            "passed-in",
            "re",
            "lost-after-kontra",
            "won-grand-hand",
            "sixty-sixty",
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


def expect_the_chips(person: Page, *chips: str) -> None:
    """The button of the rules reads these chips, in this order, and nothing else."""
    expect(chips_of(person)).to_have_text(loosely(*chips))


def sheet_of(person: Page) -> Locator:
    return person.get_by_role("dialog", name=word("rules.title"), exact=True)


def points_of(person: Page) -> Locator:
    return person.get_by_role("group", name=word("result.trickPoints"), exact=True)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_watcher_sees_the_chips_of_a_table_opened_with_options(
    looks_at: Callable[..., Page], form_factor: dict[str, Any]
) -> None:
    person = looks_at(form_factor, KONTRA_AND_BOCK)

    expect_the_chips(person, word("rules.chipPoints"), word("rules.chipKontra"), word("rules.chipBock"))


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_table_with_every_rule_shows_a_chip_for_each(
    looks_at: Callable[..., Page], form_factor: dict[str, Any]
) -> None:
    person = looks_at(form_factor, {"show_running_points": True, **EVERY_RULE})

    expect_the_chips(
        person, word("rules.chipPoints"), word("rules.chipKontra"), word("rules.chipRamsch"), word("rules.chipBock")
    )


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_both_special_rules_of_giving_up_show_one_chip_and_a_row_each(
    looks_at: Callable[..., Page], form_factor: dict[str, Any]
) -> None:
    person = looks_at(form_factor, {"give_up": {"partner_agrees": True, "any_time": True}})

    expect_the_chips(person, word("rules.chipGiveUp"))
    chips_of(person).click()
    expect(sheet_of(person).locator(".rrow b")).to_have_text(
        [word("rules.nameGiveUpPartner"), word("rules.nameGiveUpAnyTime")]
    )
    expect(sheet_of(person).locator(".rrow small span")).to_have_text(
        [word("rules.giveUpPartnerAgrees"), word("rules.giveUpAnyTime")]
    )


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_table_without_options_shows_the_chip_official_and_its_sheet_names_the_official_rules(
    looks_at: Callable[..., Page], form_factor: dict[str, Any]
) -> None:
    person = looks_at(form_factor, None)

    expect_the_chips(person, OFFICIAL)
    chips_of(person).click()
    expect(sheet_of(person)).to_be_visible()
    expect(sheet_of(person).get_by_text(word("rules.lockBadge"))).to_be_visible()
    expect(sheet_of(person).locator(".rrow b")).to_have_text([word("rules.nameOfficial")])
    expect(sheet_of(person).locator(".rrow small span")).to_have_text([word("rules.officialUnchanged")])


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


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_menus_rules_row_opens_the_sheet_and_the_focus_returns_to_the_chips(
    looks_at: Callable[..., Page], form_factor: dict[str, Any]
) -> None:
    person = looks_at(form_factor, KONTRA_AND_BOCK)

    menu_button(person, word("rules.title")).click()

    expect(sheet_of(person)).to_be_visible()
    expect(sheet_of(person).locator(".rrow b")).to_have_text(
        [word("rules.namePoints"), word("rules.nameKontra"), word("rules.nameBock")]
    )
    sheet_of(person).get_by_role("button", name=CLOSE).click()
    expect(sheet_of(person)).to_be_hidden()
    expect(chips_of(person)).to_be_focused()


def test_the_chips_are_reached_by_tab_and_opened_by_enter(looks_at: Callable[..., Page]) -> None:
    person = looks_at(DESKTOP, RUNNING_POINTS_ONLY)

    for _ in range(5):
        person.keyboard.press("Tab")
        if chips_of(person).evaluate("chips => chips === document.activeElement"):
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
    trigger_words = [
        word(f"rules.bockTrigger{trigger}")
        for trigger in (
            "SixtySixty",
            "WonGrandHand",
            "LostAfterKontra",
            "Re",
            "PassedIn",
            "Schneider",
            "Schwarz",
            "TotalEndingIn00",
        )
    ]
    expect(bock.nth(0)).to_have_text(
        word("rules.bockTriggers", triggers=f"{', '.join(trigger_words[:-1])} und {trigger_words[-1]}")
    )


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
        for side, points in ((declarer_side, declarer_points), (opponents_side, opponents_points)):
            counted = word("result.sidePoints", side=side, points=str(points))
            expect(points_of(person).get_by_text(counted, exact=True)).to_be_visible()


@pytest.fixture
def deal_with_running_points(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    def deal(
        form_factor: dict[str, Any],
        game: str = "kreuz",
        joiners: tuple[str, str] = ("ben", "cleo"),
        opener_name: str = "anna",
    ) -> PlayingTable:
        return deal_playing_table(
            open_person,
            e2e_server,
            member_of,
            page_errors,
            form_factor,
            game=game,
            running_points=True,
            joiners=joiners,
            opener_name=opener_name,
        )

    return deal


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_plaque_counts_from_completed_tricks_for_the_players_and_a_watcher(
    deal_with_running_points: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_with_running_points(form_factor)

    expect_the_bar(table, 0, 0)
    for person in table.everyone:
        expect_the_chips(person, word("rules.chipPoints"))
    table.play_out(CARDS_IN_A_TRICK - 1)
    expect_the_bar(table, 0, 0)
    table.play_out(1)

    counted = table.playing()["running_points"]
    expect_the_bar(table, counted["declarer"], counted["opponents"])


def test_the_bar_stays_beside_a_standing_give_up_request(
    deal_with_running_points: Callable[..., PlayingTable],
) -> None:
    table = deal_with_running_points(DESKTOP)
    table.play_out(CARDS_AFTER_TWO_TRICKS)
    counted = table.playing()["running_points"]

    table.declaring.step(table.declarer_seat, TABLE_GIVE_UP_SUFFIX)

    for person in table.everyone:
        expect(old_surface.requests(person)).to_be_visible()
    expect_the_bar(table, counted["declarer"], counted["opponents"])


def test_a_null_game_shows_no_bar(deal_with_running_points: Callable[..., PlayingTable]) -> None:
    table = deal_with_running_points(DESKTOP, "null")

    for person in table.everyone:
        expect(person.get_by_text(word("game.null"), exact=True)).to_be_visible()
        expect(points_of(person)).to_have_count(0)


def test_a_table_opened_without_the_switch_shows_no_bar(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="anna", **DESKTOP), page_errors)

    open_new_table(person, e2e_server)

    expect_the_chips(person, OFFICIAL)
    expect(points_of(person)).to_have_count(0)
