from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from skat.web.calling import AGENT_ADDERS_GROUP
from skat.web.playing import TABLE_GIVE_UP_SUFFIX
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_PAGE_PREFIX, TABLE_SIT_SUFFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.call_frame import (
    CALL_HOST,
    CALL_ORIGIN,
    CALL_PORT,
    CHAIR,
    FRAME,
    FRAME_REFUSED,
    HTTP_OK,
    OTHER_HOST,
    OTHER_PORT,
    THREE_CHAIRS,
    call_label,
    new_table,
    page_holding,
    serve_on_the_frame_site,
    served_from,
    table_url,
)
from tests.e2e.support.early_end import CARDS_AFTER_TWO_TRICKS, REQUEST
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.listening_agent import ListeningAgent
from tests.e2e.support.people import SMALL_PHONE
from tests.e2e.support.table_menu import menu_button, open_agents_panel
from tests.e2e.support.tables import open_new_table, table_id_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from playwright.sync_api import FrameLocator, Page

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

HTTP_FORBIDDEN = 403
LANDSCAPE_PHONE = {"viewport": {"width": 844, "height": 390}, "is_mobile": True, "has_touch": True}
# The call page sizes its frame: the screen's width and the height its own page leaves (676 of 740 px, 326 of 390 px).
SMALL_FRAME = "width:360px;height:676px"
LANDSCAPE_FRAME = "width:844px;height:326px"
MORE = text(SOURCE_LANGUAGE, "table.menu")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
# A simple request: no preflight stops it, so it reaches the server whatever the origin.
SIMPLE_POST = """([url, body]) => fetch(url, {
    method: "POST", mode: "no-cors", credentials: "include", headers: {"content-type": "text/plain"}, body
}).then(() => undefined)"""


@pytest.fixture(scope="module")
def call_origin() -> str:
    return CALL_ORIGIN


@pytest.fixture(scope="module")
def framing_server(
    e2e_server: RunningServer, tmp_path_factory: pytest.TempPathFactory, call_origin: str
) -> Iterator[RunningServer]:
    yield from serve_on_the_frame_site(e2e_server, tmp_path_factory.mktemp("framing"), call_origin=call_origin)


@pytest.fixture(scope="module")
def unframed_server(e2e_server: RunningServer, tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    yield from serve_on_the_frame_site(e2e_server, tmp_path_factory.mktemp("unframed"))


CALL_PAGE_WITHOUT_FRAME = "<!doctype html><title>call</title>"


def table_answer(person: Page, server: RunningServer, path: str) -> dict[str, object]:
    return person.request.get(f"{server.base_url}{TABLES_PATH}/{table_id_of(path)}").json()


def seating_of(answer: dict[str, object]) -> tuple[object, list[dict[str, object]]]:
    """The table's version and its chairs without whether their members are connected, which moves on its own."""
    chairs: list[dict[str, object]] = answer["chairs"]  # type: ignore[assignment]
    return answer["version"], [{name: value for name, value in chair.items() if name != "is_away"} for chair in chairs]


REFUSED_FRAMES = [
    pytest.param("unframed_server", lambda call_origin: call_origin, id="unset-setting"),
    pytest.param("framing_server", lambda _call_origin: f"https://{OTHER_HOST}:{CALL_PORT}", id="other-host"),
    pytest.param("framing_server", lambda _call_origin: f"https://{CALL_HOST}:{OTHER_PORT}", id="other-port"),
]


@pytest.mark.parametrize(("server_name", "framing_origin"), REFUSED_FRAMES)
def test_a_table_stays_out_of_every_frame_but_the_configured_call_origins(
    request: pytest.FixtureRequest,
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    expected_request_failures: list[str],
    call_origin: str,
    server_name: str,
    framing_origin: Callable[[str], str],
) -> None:
    server: RunningServer = request.getfixturevalue(server_name)
    path = new_table(open_person, server)
    expected_request_failures.append(table_url(server, path))
    origin = framing_origin(call_origin)
    visitor = open_person(server=server)

    with (
        served_from(origin, visitor, browser_coverage, page_holding(table_url(server, path))),
        visitor.expect_console_message(lambda message: FRAME_REFUSED in message.text),
    ):
        visitor.goto(f"{origin}/")

    expect(visitor.locator(FRAME)).to_be_attached()
    expect(visitor.frame_locator(FRAME).locator(CHAIR)).to_have_count(0)


def test_the_call_origin_shows_the_table_signed_in_and_the_frame_reads_and_streams_as_the_page_does(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    call_origin: str,
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server)
    read_address = f"{framing_server.base_url}{TABLES_PATH}/{table_id_of(path)}"

    with served_from(call_origin, visitor, browser_coverage, page_holding(table_url(framing_server, path))):
        with (
            visitor.expect_response(lambda response: response.url == read_address) as read,
            visitor.expect_response(lambda response: response.url == read_address + TABLE_EVENTS_SUFFIX) as stream,
        ):
            visitor.goto(f"{call_origin}/")
        expect(visitor.frame_locator(FRAME).locator(CHAIR)).to_have_count(THREE_CHAIRS)

    assert (read.value.status, stream.value.status) == (HTTP_OK, HTTP_OK)


def test_a_request_the_call_page_sends_to_skat_is_refused_and_takes_no_chair(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    call_origin: str,
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server)
    before = seating_of(table_answer(visitor, framing_server, path))
    sit_address = f"{framing_server.base_url}{TABLES_PATH}/{table_id_of(path)}{TABLE_SIT_SUFFIX}"

    with served_from(call_origin, visitor, browser_coverage, CALL_PAGE_WITHOUT_FRAME):
        visitor.goto(f"{call_origin}/")
        with visitor.expect_response(lambda response: response.url == sit_address) as sit:
            visitor.evaluate(SIMPLE_POST, [sit_address, '{"command_id": "call-sit-0001", "seat": 1}'])

    assert sit.value.status == HTTP_FORBIDDEN
    assert seating_of(table_answer(visitor, framing_server, path)) == before


@contextmanager
def framed_at(
    visitor: Page, browser_coverage: BrowserCoverage, address: str, frame_style: str
) -> Iterator[FrameLocator]:
    """The call page of `page_holding` with a frame of `frame_style`, reached as the call origin reaches it."""
    with served_from(CALL_ORIGIN, visitor, browser_coverage, page_holding(address, style=frame_style)):
        visitor.evaluate("url => location.assign(url)", f"{CALL_ORIGIN}/")
        yield visitor.frame_locator(FRAME)


@pytest.mark.usefixtures("framing_issuer_reusing_refresh_tokens")
def test_a_give_up_request_in_a_360_wide_frame_leaves_the_menu_key_in_reach_without_scrolling(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
) -> None:
    table = deal_playing_table(
        open_person,
        framing_server,
        member_of,
        page_errors,
        {**SMALL_PHONE, "server": framing_server, "groups": (AGENT_ADDERS_GROUP,)},
    )
    table.play_out(CARDS_AFTER_TWO_TRICKS)
    asked = next(seat for seat in table.pages if seat != table.declarer_seat)
    person = table.pages[asked]
    address = table_url(framing_server, f"{TABLE_PAGE_PREFIX}{table.declaring.table_id}")

    with framed_at(person, browser_coverage, address, SMALL_FRAME) as call:
        table.declaring.step(table.declarer_seat, TABLE_GIVE_UP_SUFFIX)
        expect(call.locator(REQUEST)).to_be_visible()

        expect(call.get_by_role("button", name=MORE)).to_be_in_viewport(ratio=1)
        expect(menu_button(call, STAND_UP)).to_be_visible()
    assert page_errors == []


@pytest.mark.usefixtures("framing_issuer_reusing_refresh_tokens")
def test_the_agents_panel_in_a_landscape_frame_offers_both_agents_without_scrolling(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
) -> None:
    felix = record_page_errors(
        open_person(username="felix-landscape", groups=(AGENT_ADDERS_GROUP,), server=framing_server, **LANDSCAPE_PHONE),
        page_errors,
    )
    path = open_new_table(felix, framing_server)
    owner = member_of(felix).account.id
    agents = [
        ListeningAgent(framing_server, owner, name, f"agent-subject-{name.lower()}-landscape")
        for name in ("Mozart", "Leonardo")
    ]
    try:
        with framed_at(felix, browser_coverage, table_url(framing_server, path), LANDSCAPE_FRAME) as call:
            # Read before the panel is opened: a tap scrolls the frame and would bring a key below the fold into view.
            expect(call.get_by_role("button", name=MORE)).to_be_in_viewport(ratio=1)
            open_agents_panel(call)

            for name in ("Mozart", "Leonardo"):
                row = call.get_by_role("button", name=call_label(name))
                expect(row).to_be_in_viewport(ratio=1)
                row.click(trial=True)
    finally:
        for agent in agents:
            agent.close()
    assert page_errors == []
