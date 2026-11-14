import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.engine.kontra import KontraDeadline, KontraReach, KontraSayer
from skat.table.records import SERIES_LENGTH_DEFAULT, OccupantKind
from skat.web.lobby import (
    LOBBY_EVENTS_PATH,
    LobbyChairAnswer,
    LobbyTableAnswer,
    MineAnswer,
    OpenAnswer,
    OpenChairAnswer,
    OpenTableAnswer,
)
from skat.web.table_options import KontraOptionsAnswer, OptionsAnswer
from skat.web.tables import TABLE_SIT_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import NEW_TABLE_BUTTON, record_page_errors
from tests.e2e.support.people import DESKTOP, WIDTHS
from tests.e2e.support.tables import (
    TABLE_URL,
    assert_never_reloaded,
    mark_page,
    open_start_page,
    plate_of,
    sit_in,
    watch,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from skat.web.words import Language
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

OPEN_TABLES = text(SOURCE_LANGUAGE, "lobby.openTables")
MY_TABLES = text(SOURCE_LANGUAGE, "lobby.myTables")
NO_OPEN_TABLE = text(SOURCE_LANGUAGE, "lobby.noOpenTables")
SEAT_FREE = text(SOURCE_LANGUAGE, "lobby.seatFree")
YOU = text(SOURCE_LANGUAGE, "lobby.sideYou")
PRIVATE = text(SOURCE_LANGUAGE, "lobby.private")
GAME_WAITS = text(SOURCE_LANGUAGE, "lobby.chipGameWaits")
PAUSED = text(SOURCE_LANGUAGE, "lobby.chipPaused")
CHIP_KONTRA = text(SOURCE_LANGUAGE, "rules.chipKontra")
CHIP_OFFICIAL = text(SOURCE_LANGUAGE, "rules.chipOfficial")
VISIBILITY = text(SOURCE_LANGUAGE, "start.visibility")
VISIBILITY_OPEN = text(SOURCE_LANGUAGE, "start.visibilityOpen")
VISIBILITY_PRIVATE = text(SOURCE_LANGUAGE, "start.visibilityPrivate")
VISIBILITY_INFO_BUTTON = text(SOURCE_LANGUAGE, "start.visibilityInfoButton")
VISIBILITY_INFO = text(SOURCE_LANGUAGE, "start.visibilityInfo")
OPEN_TABLE = text(SOURCE_LANGUAGE, "start.openTable")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
CLOSE_KEY = text(SOURCE_LANGUAGE, "table.close")
CLOSE_CONFIRM = text(SOURCE_LANGUAGE, "table.closeConfirm")
ENGLISH: Language = "en"
EVENT_STREAM = "text/event-stream"
# A tap target is at least this many CSS pixels on each side.
TAP_TARGET_PIXELS = 44


def name_at(base: str, form_factor: dict[str, Any]) -> str:
    """An account name no other width of this test uses, so each run's table has its own title."""
    return f"{base}{form_factor['viewport']['width']}"


def title_of(owner: str, language: Language = SOURCE_LANGUAGE) -> str:
    return text(language, "lobby.titleSibilant" if owner.endswith("s") else "lobby.title", name=owner)


def open_card(person: Page, owner: str, language: Language = SOURCE_LANGUAGE) -> Locator:
    """The entry of the open table `owner` opened, which is no link."""
    return person.locator("article.lobby-card").filter(
        has=person.get_by_role("heading", name=title_of(owner, language))
    )


def sit_buttons_of(card: Locator) -> Locator:
    return card.locator("button.lobby-sit")


def plates_of(card: Locator) -> Locator:
    return card.locator(".lobby-plate b")


def pick_visibility(person: Page, visibility: str) -> None:
    person.get_by_role("radiogroup", name=VISIBILITY).get_by_role("radio", name=visibility).check()


def open_private_table(person: Page, server: RunningServer) -> str:
    person.goto(f"{server.base_url}/")
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    pick_visibility(person, VISIBILITY_PRIVATE)
    person.get_by_role("button", name=OPEN_TABLE).click()
    expect(person).to_have_url(TABLE_URL)
    return person.url.removeprefix(server.base_url)


def stream_event(name: str, answer: str) -> str:
    return f"event: {name}\ndata: {answer}\n\n"


def stream_of(*, mine: str = '{"tables":[]}', open_tables: list[OpenTableAnswer]) -> str:
    return stream_event("mine", mine) + stream_event("open", OpenAnswer(tables=open_tables).model_dump_json())


def serve_stream(person: Page, body: str) -> None:
    """The lobby stream answers the page with this body and ends, as a stream the network cuts does."""
    person.route(
        f"**{LOBBY_EVENTS_PATH}",
        lambda route: route.fulfill(status=200, headers={"content-type": EVENT_STREAM}, body=body),
    )


def open_table_answer(
    opener: str,
    *,
    options: OptionsAnswer | None = None,
    names: tuple[str | None, ...] = (None, None, None),
    away_hold: dict[int, int] | None = None,
    waiting_seat: int | None = None,
    ends_at: datetime | None = None,
) -> OpenTableAnswer:
    holds = away_hold or {}
    chairs = [
        OpenChairAnswer(
            seat=seat,
            occupant_name=name,
            occupant_kind=None if name is None else OccupantKind.PERSON,
            is_away=seat in holds,
            hold_seconds_left=holds.get(seat),
        )
        for seat, name in enumerate(names)
    ]
    return OpenTableAnswer(
        id=f"{ord(opener[0]):x}".ljust(32, "e"),
        title_name=opener,
        game_number=0,
        game_count=SERIES_LENGTH_DEFAULT,
        options=options or OptionsAnswer(show_running_points=False, kontra=None, bock=None, ramsch=None),
        watchers=0,
        free_chairs=sum(name is None for name in names),
        dealt=ends_at is not None or waiting_seat is not None,
        waiting_seat=waiting_seat,
        ends_at=ends_at,
        chairs=chairs,
    )


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_new_table_sheet_offers_open_checked_by_default_and_private_with_a_line_that_names_both(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    person = record_page_errors(open_person(username=name_at("Ludwig", form_factor), **form_factor), page_errors)
    person.goto(f"{e2e_server.base_url}/")

    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()

    choice = person.get_by_role("radiogroup", name=VISIBILITY)
    expect(choice.get_by_role("radio", name=VISIBILITY_OPEN)).to_be_checked()
    expect(choice.get_by_role("radio", name=VISIBILITY_PRIVATE)).not_to_be_checked()
    expect(person.get_by_text(VISIBILITY_INFO)).to_have_count(0)
    person.get_by_role("button", name=VISIBILITY_INFO_BUTTON).click()
    expect(person.get_by_text(VISIBILITY_INFO)).to_be_visible()
    pick_visibility(person, VISIBILITY_PRIVATE)
    expect(choice.get_by_role("radio", name=VISIBILITY_OPEN)).not_to_be_checked()
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_private_table_shows_its_lock_to_its_chair_holder_and_no_other_member_is_offered_it(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    owner_name = name_at("Mathilde", form_factor)
    owner = record_page_errors(open_person(username=owner_name, **form_factor), page_errors)
    other = record_page_errors(open_person(username=name_at("Norbert", form_factor), **form_factor), page_errors)
    path = open_private_table(owner, e2e_server)

    open_start_page(owner, e2e_server)
    open_start_page(other, e2e_server)

    mine = owner.locator(f"a.lobby-card[href='{path}']")
    expect(mine).to_have_count(1)
    expect(mine.get_by_role("img", name=PRIVATE)).to_be_visible()
    expect(other.get_by_role("heading", name=OPEN_TABLES)).to_be_visible()
    expect(other.get_by_role("heading", name=title_of(owner_name))).to_have_count(0)
    other.goto(f"{e2e_server.base_url}{path}")
    expect(other.locator(".chair")).to_have_count(3)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_open_table_is_listed_to_another_member_and_one_tap_on_frei_seats_him_and_opens_the_table(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    owner_name, guest_name = name_at("Olivia", form_factor), name_at("Paul", form_factor)
    owner = record_page_errors(open_person(username=owner_name, **form_factor), page_errors)
    guest = record_page_errors(open_person(username=guest_name, **form_factor), page_errors)
    owner.goto(f"{e2e_server.base_url}/")
    owner.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    owner.get_by_role("button", name=OPEN_TABLE).click()
    expect(owner).to_have_url(TABLE_URL)
    expect(owner.locator(".chair")).to_have_count(3)

    open_start_page(guest, e2e_server)

    expect(guest.get_by_role("heading", name=OPEN_TABLES)).to_be_visible()
    card = open_card(guest, owner_name)
    expect(card).to_have_count(1)
    expect(card).to_contain_text(text(SOURCE_LANGUAGE, "lobby.length", count=SERIES_LENGTH_DEFAULT))
    expect(card).to_contain_text(CHIP_OFFICIAL)
    expect(plates_of(card)).to_have_text([owner_name, SEAT_FREE, SEAT_FREE])
    expect(sit_buttons_of(card)).to_have_count(2)
    assert guest.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    box = sit_buttons_of(card).first.bounding_box()
    assert box is not None
    assert box["width"] >= TAP_TARGET_PIXELS
    assert box["height"] >= TAP_TARGET_PIXELS
    assert box["x"] + box["width"] <= form_factor["viewport"]["width"]

    plates_of(card).filter(has_text=SEAT_FREE).first.click()

    expect(guest).to_have_url(TABLE_URL)
    expect(plate_of(owner, 2)).to_contain_text(guest_name)


def test_the_list_follows_create_sit_stand_and_close_without_a_reload(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    owner_name = "Quirin"
    watcher = record_page_errors(open_person(username="Rosa", **DESKTOP), page_errors)
    owner = record_page_errors(open_person(username=owner_name, **DESKTOP), page_errors)
    sitter = record_page_errors(open_person(username="Sven", **DESKTOP), page_errors)
    open_start_page(watcher, e2e_server)
    expect(watcher.get_by_role("heading", name=OPEN_TABLES)).to_be_visible()
    mark_page(watcher)

    owner.goto(f"{e2e_server.base_url}/")
    owner.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    owner.get_by_role("button", name=OPEN_TABLE).click()
    expect(owner).to_have_url(TABLE_URL)
    path = owner.url.removeprefix(e2e_server.base_url)

    card = open_card(watcher, owner_name)
    expect(plates_of(card)).to_have_text([owner_name, SEAT_FREE, SEAT_FREE])
    watch(sitter, e2e_server, path)
    sit_in(sitter, 2)
    expect(plates_of(card)).to_have_text([owner_name, "Sven", SEAT_FREE])
    expect(sit_buttons_of(card)).to_have_count(1)
    sitter.get_by_role("button", name=STAND_UP).click()
    expect(plates_of(card)).to_have_text([owner_name, SEAT_FREE, SEAT_FREE])
    owner.locator(".actions").get_by_role("button", name=CLOSE_KEY, exact=True).click()
    owner.get_by_role("button", name=CLOSE_CONFIRM, exact=True).click()
    expect(card).to_have_count(0)
    assert_never_reloaded(watcher)


def test_a_full_table_shows_its_three_names_and_no_free_chair(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    owner = record_page_errors(open_person(username="Theo", **DESKTOP), page_errors)
    guests = [record_page_errors(open_person(username=name, **DESKTOP), page_errors) for name in ("Uwe", "Vera")]
    onlooker = record_page_errors(open_person(username="Wanda", **DESKTOP), page_errors)
    owner.goto(f"{e2e_server.base_url}/")
    owner.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    owner.get_by_role("button", name=OPEN_TABLE).click()
    expect(owner).to_have_url(TABLE_URL)
    path = owner.url.removeprefix(e2e_server.base_url)
    for seat, guest in enumerate(guests, start=2):
        watch(guest, e2e_server, path)
        sit_in(guest, seat)

    open_start_page(onlooker, e2e_server)

    card = open_card(onlooker, "Theo")
    expect(plates_of(card)).to_have_text(["Theo", "Uwe", "Vera"])
    expect(sit_buttons_of(card)).to_have_count(0)


def test_the_open_section_says_so_when_no_other_table_is_open(
    open_person: Callable[..., Page], e2e_server: RunningServer, expected_request_failures: list[str]
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(username="Xaver", **DESKTOP)
    serve_stream(person, stream_of(open_tables=[]))

    person.goto(f"{e2e_server.base_url}/")

    expect(person.get_by_role("heading", name=OPEN_TABLES)).to_be_visible()
    expect(person.get_by_role("status").filter(has_text=NO_OPEN_TABLE)).to_be_visible()
    expect(person.get_by_role("heading", name=MY_TABLES)).to_have_count(0)


def test_an_open_entry_shows_its_rules_its_state_and_the_minutes_an_away_chair_is_held(
    open_person: Callable[..., Page], e2e_server: RunningServer, expected_request_failures: list[str]
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(username="Yara", **DESKTOP)
    kontra = OptionsAnswer(
        show_running_points=False,
        kontra=KontraOptionsAnswer(
            sayer=KontraSayer.ANY_OPPONENT, reach=KontraReach.KONTRA_RE, deadline=KontraDeadline.OWN_CARD
        ),
        bock=None,
        ramsch=None,
    )
    serve_stream(
        person,
        stream_of(
            open_tables=[
                open_table_answer("Zora", options=kontra, names=("Zora", "Zeno", None), waiting_seat=2),
                open_table_answer("Ines", names=("Ines", None, None), away_hold={0: 240}),
                open_table_answer("Jonas", names=("Jonas", "Jana", None), ends_at=datetime(2027, 1, 1, tzinfo=UTC)),
            ]
        ),
    )

    person.goto(f"{e2e_server.base_url}/")

    waits = open_card(person, "Zora")
    expect(waits).to_contain_text(CHIP_KONTRA)
    expect(waits).to_contain_text(GAME_WAITS)
    held = open_card(person, "Ines")
    expect(held.locator(".lobby-plate small")).to_have_text(
        text(SOURCE_LANGUAGE, "lobby.minutesLeft", count=4, minutes="4")
    )
    expect(held.locator(".lobby-seat.away")).to_have_count(1)
    paused = open_card(person, "Jonas")
    expect(paused).to_contain_text(PAUSED)


def private_table_answer(owner: str) -> LobbyTableAnswer:
    chairs = [
        LobbyChairAnswer(
            seat=seat,
            occupant_name=owner if seat == 0 else None,
            occupant_kind=OccupantKind.PERSON if seat == 0 else None,
            is_mine=seat == 0,
            ready=False,
            total=None,
            is_away=False,
            is_turn=False,
            hold_seconds_left=None,
        )
        for seat in range(3)
    ]
    return LobbyTableAnswer(
        id=f"{ord(owner[0]):x}".ljust(32, "d"),
        private=True,
        title_name=owner,
        game_number=0,
        game_count=SERIES_LENGTH_DEFAULT,
        dealt=False,
        awaits_you=False,
        waits_on=None,
        result_waits=False,
        series_over=False,
        ends_at=None,
        chairs=chairs,
    )


def expect_no_german(person: Page, *keys: str) -> None:
    """The page shows none of these catalog keys' German wording, matched as whole words."""
    for key in keys:
        german = text(SOURCE_LANGUAGE, key)
        expect(person.locator("body")).not_to_contain_text(re.compile(rf"\b{re.escape(german)}\b"))


def test_the_visibility_sheet_reads_in_english_and_leaks_no_german(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    person = record_page_errors(open_person(username="Quirin", locale=ENGLISH, **DESKTOP), page_errors)
    person.goto(f"{e2e_server.base_url}/")

    person.get_by_role("button", name=text(ENGLISH, "start.newTable")).click()

    choice = person.get_by_role("radiogroup", name=text(ENGLISH, "start.visibility"))
    expect(choice.get_by_role("radio", name=text(ENGLISH, "start.visibilityOpen"))).to_be_checked()
    expect(choice.get_by_role("radio", name=text(ENGLISH, "start.visibilityPrivate"))).not_to_be_checked()
    person.get_by_role("button", name=text(ENGLISH, "start.visibilityInfoButton")).click()
    expect(person.get_by_text(text(ENGLISH, "start.visibilityInfo"))).to_be_visible()
    expect_no_german(
        person, "start.visibility", "start.visibilityOpen", "start.visibilityPrivate", "start.visibilityInfo"
    )


def test_the_lobby_reads_in_english_and_leaks_no_german(
    open_person: Callable[..., Page], e2e_server: RunningServer, expected_request_failures: list[str]
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(username="Rosa", locale=ENGLISH, **DESKTOP)
    serve_stream(
        person,
        stream_of(
            mine=MineAnswer(tables=[private_table_answer("Rosa")]).model_dump_json(),
            open_tables=[
                open_table_answer("Zora", names=("Zora", "Zeno", None), waiting_seat=2),
                open_table_answer("Jonas", names=("Jonas", "Jana", None), ends_at=datetime(2027, 1, 1, tzinfo=UTC)),
            ],
        ),
    )

    person.goto(f"{e2e_server.base_url}/")

    expect(person.get_by_role("heading", name=text(ENGLISH, "lobby.openTables"))).to_be_visible()
    expect(person.get_by_role("img", name=text(ENGLISH, "lobby.private"))).to_be_visible()
    waits = open_card(person, "Zora", ENGLISH)
    expect(waits).to_contain_text(text(ENGLISH, "lobby.chipGameWaits"))
    expect(
        waits.get_by_role("button", name=text(ENGLISH, "lobby.sitAt", title=title_of("Zora", ENGLISH)))
    ).to_have_count(1)
    expect(open_card(person, "Jonas", ENGLISH)).to_contain_text(text(ENGLISH, "lobby.chipPaused"))
    expect_no_german(person, "lobby.openTables", "lobby.chipGameWaits", "lobby.chipPaused")


def test_a_refused_sit_reads_in_english(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str]
) -> None:
    owner = record_page_errors(open_person(username="Zora", **DESKTOP), page_errors)
    guest = open_person(username="Sibylle", locale=ENGLISH, **DESKTOP)
    owner.goto(f"{e2e_server.base_url}/")
    owner.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    owner.get_by_role("button", name=OPEN_TABLE).click()
    expect(owner).to_have_url(TABLE_URL)
    guest.route(
        f"**{TABLE_SIT_SUFFIX}", lambda route: route.fulfill(status=422, content_type="application/json", body="{}")
    )
    guest.goto(f"{e2e_server.base_url}/")

    open_card(guest, "Zora", ENGLISH).get_by_role("button").first.click()

    expect(guest.get_by_role("alert")).to_have_text(text(ENGLISH, "lobby.sitFailed"))
    expect_no_german(guest, "lobby.sitFailed")


def test_the_empty_open_list_reads_in_english(
    open_person: Callable[..., Page], e2e_server: RunningServer, expected_request_failures: list[str]
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{LOBBY_EVENTS_PATH}")
    person = open_person(username="Tilda", locale=ENGLISH, **DESKTOP)
    serve_stream(person, stream_of(open_tables=[]))

    person.goto(f"{e2e_server.base_url}/")

    expect(person.get_by_role("status").filter(has_text=text(ENGLISH, "lobby.noOpenTables"))).to_be_visible()
    expect_no_german(person, "lobby.noOpenTables")
