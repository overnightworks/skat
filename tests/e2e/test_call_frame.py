from contextlib import contextmanager, nullcontext
from typing import TYPE_CHECKING, Any

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
    new_table,
    page_holding,
    serve_on_the_frame_site,
    served_from,
    table_url,
)
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.listening_agent import ListeningAgent
from tests.e2e.support.people import DESKTOP, PHONE
from tests.e2e.support.tables import open_new_table, table_id_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from playwright.sync_api import FrameLocator, Page

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

HTTP_FORBIDDEN = 403
SMALL_PHONE = {"viewport": {"width": 360, "height": 740}, "is_mobile": True, "has_touch": True}
LANDSCAPE_PHONE = {"viewport": {"width": 844, "height": 390}, "is_mobile": True, "has_touch": True}
# The call page sizes its frame: the screen's width and the height its own page leaves (676 of 740 px, 326 of 390 px).
SMALL_FRAME = "width:360px;height:676px"
PHONE_FRAME = "width:390px;height:780px"
LANDSCAPE_FRAME = "width:844px;height:326px"
# The small phone, taller than any short call frame: its chairs and trick keep the sizes a standalone page draws.
TALLER_PHONE_VIEWPORT = {"width": 360, "height": 1000}
TRICK = ".trick"
PILL = text(SOURCE_LANGUAGE, "agents.pill")
STAND_UP = text(SOURCE_LANGUAGE, "table.standUp")
SPEAKER = ".actions .sound-button"
# A call's strip holds stand up, the agents pill and the speaker.
CALL_STRIP_ITEMS = 3
STRIP = ".actions"
STATUS = ".plaque"
NOTICE = ".notice"
CARDS_AFTER_TWO_TRICKS = 6
INVITATION_WITHIN_SECONDS = 15
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


def call_label(name: str) -> str:
    return text(SOURCE_LANGUAGE, "agents.callLabel", name=name)


def sits_note(name: str) -> str:
    return text(SOURCE_LANGUAGE, "table.agentSits", name=name)


def box_of(locator: Any) -> dict[str, float]:
    box = locator.bounding_box()
    assert box is not None, f"{locator} has no box"
    return box


def bottom_of(box: dict[str, float]) -> float:
    return box["y"] + box["height"]


@pytest.fixture
def framing_issuer_reusing_refresh_tokens(framing_server: RunningServer) -> Iterator[None]:
    # The realm lets a refresh token be used again, so overlapping reads of one session both succeed.
    framing_server.issuer.reuses_refresh_tokens = True
    yield
    framing_server.issuer.reuses_refresh_tokens = False


@pytest.mark.usefixtures("framing_issuer_reusing_refresh_tokens")
def test_a_give_up_request_in_a_360_wide_frame_keeps_the_call_strip_and_its_pill_inside_the_frame(
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
        expect(call.locator(".plaque.ask")).to_be_visible()

        frame = box_of(person.locator(FRAME))
        for part in (call.get_by_role("button", name=PILL), call.locator(STRIP)):
            box = box_of(part)
            assert box["y"] >= frame["y"]
            assert bottom_of(box) <= bottom_of(frame)
    assert page_errors == []


@pytest.mark.usefixtures("framing_issuer_reusing_refresh_tokens")
def test_an_open_agents_list_in_a_landscape_frame_shows_both_rows_above_the_call_strip(
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
            # Measured before the pill is tapped: a tap scrolls the frame and would hide a strip below the fold.
            frame = box_of(felix.locator(FRAME))
            strip = box_of(call.locator(STRIP))
            assert bottom_of(strip) <= bottom_of(frame)
            call.get_by_role("button", name=PILL).click()
            for name in ("Mozart", "Leonardo"):
                expect(call.get_by_role("button", name=call_label(name))).to_be_visible()

            for name in ("Mozart", "Leonardo"):
                row = box_of(call.get_by_role("button", name=call_label(name)))
                assert row["y"] >= frame["y"]
                assert bottom_of(row) <= strip["y"]
    finally:
        for agent in agents:
            agent.close()
    assert page_errors == []


@pytest.mark.usefixtures("framing_issuer_reusing_refresh_tokens")
@pytest.mark.parametrize("framed", [True, False], ids=["framed", "standalone"])
@pytest.mark.parametrize("form_factor", [PHONE, DESKTOP], ids=["390", "1280"])
def test_an_agent_sitting_notice_stands_under_the_status_line(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
    framed: bool,
    form_factor: dict[str, Any],
) -> None:
    felix = record_page_errors(
        open_person(username="felix-notice", groups=(AGENT_ADDERS_GROUP,), server=framing_server, **form_factor),
        page_errors,
    )
    path = open_new_table(felix, framing_server)
    agent = ListeningAgent(framing_server, member_of(felix).account.id, "Leonardo", "agent-subject-leonardo-notice")
    viewport = felix.viewport_size
    assert viewport is not None
    frame_style = f"width:{viewport['width']}px;height:{viewport['height']}px"
    try:
        with (
            framed_at(felix, browser_coverage, table_url(framing_server, path), frame_style)
            if framed
            else nullcontext(felix)
        ) as scope:
            scope.get_by_role("button", name=PILL).click()
            scope.get_by_role("button", name=call_label("Leonardo")).click()
            agent.accept(agent.invitation_within(felix, INVITATION_WITHIN_SECONDS))

            notice = box_of(scope.locator(NOTICE, has_text=sits_note("Leonardo")))
            status = box_of(scope.locator(STATUS).first)
            assert notice["y"] >= bottom_of(status)
    finally:
        agent.close()
    assert page_errors == []


@pytest.mark.usefixtures("framing_issuer_reusing_refresh_tokens")
def test_a_framed_call_strip_at_390_holds_stand_up_the_agents_pill_and_the_speaker_in_one_row(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
) -> None:
    felix = record_page_errors(
        open_person(username="felix-strip", groups=(AGENT_ADDERS_GROUP,), server=framing_server, **PHONE), page_errors
    )
    path = open_new_table(felix, framing_server)

    with framed_at(felix, browser_coverage, table_url(framing_server, path), "width:390px;height:844px") as call:
        bar = call.locator(f"{STRIP} > :not([popover])")
        expect(bar).to_have_count(CALL_STRIP_ITEMS)
        expect(call.get_by_role("button", name=STAND_UP)).to_be_visible()
        pill = box_of(call.get_by_role("button", name=PILL))
        speaker = box_of(call.locator(SPEAKER))
        assert pill["x"] < speaker["x"]
        assert bar.evaluate_all("tags => new Set(tags.map(tag => tag.offsetTop)).size") == 1
    assert page_errors == []


def chair_and_trick_sizes(person: Page | FrameLocator) -> tuple[float, float]:
    chair = box_of(person.locator(CHAIR).first)
    trick = box_of(person.locator(TRICK).first)
    return chair["width"], trick["height"]


def test_a_standalone_phone_at_360_by_740_keeps_the_chair_and_trick_sizes_of_a_taller_phone(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    framing_server: RunningServer,
    page_errors: list[str],
) -> None:
    table = deal_playing_table(
        open_person, framing_server, member_of, page_errors, {**SMALL_PHONE, "server": framing_server}
    )
    person = table.pages[table.declarer_seat]

    short = chair_and_trick_sizes(person)
    person.set_viewport_size(TALLER_PHONE_VIEWPORT)

    assert chair_and_trick_sizes(person) == pytest.approx(short)
    assert page_errors == []


@pytest.mark.usefixtures("framing_issuer_reusing_refresh_tokens")
def test_a_framed_call_at_390_by_780_keeps_the_chair_and_trick_sizes_of_a_taller_frame(
    open_person: Callable[..., Page],
    member_of: Callable[[Page], SeededMember],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    page_errors: list[str],
) -> None:
    table = deal_playing_table(open_person, framing_server, member_of, page_errors, {**PHONE, "server": framing_server})
    person = table.pages[table.declarer_seat]
    address = table_url(framing_server, f"{TABLE_PAGE_PREFIX}{table.declaring.table_id}")

    with framed_at(person, browser_coverage, address, PHONE_FRAME) as call:
        expect(call.locator(CHAIR).first).to_be_visible()
        short = chair_and_trick_sizes(call)
        person.locator(FRAME).evaluate("frame => { frame.style.height = '844px'; }")

        assert chair_and_trick_sizes(call) == pytest.approx(short)
    assert page_errors == []
