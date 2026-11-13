from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from skat.web.call import CALL_ORIGIN_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.call_frame import (
    CALL_ORIGIN,
    CHAIR,
    FRAME,
    OTHER_HOST,
    OTHER_PORT,
    THREE_CHAIRS,
    greeting_page_holding,
    new_table,
    serve_on_the_frame_site,
    served_from,
    table_url,
)
from tests.e2e.support.kit_words import kit_text
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.tables import SIT_DOWN, table_id_of

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator

    from playwright.sync_api import Frame, Page

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

BAR = ".bar"
SEAT_FREE = text(SOURCE_LANGUAGE, "table.seatFree")
YOU = text(SOURCE_LANGUAGE, "table.sideYou")
OTHER_ORIGIN = f"https://{OTHER_HOST}:{OTHER_PORT}"
VALID_HELLO = {"v": 1, "type": "hello", "attachment": 1, "attempt": None}
LOG_IN = kit_text("signIn.logIn")
MEGABYTE = 1_000_000
RECORDED_MESSAGES = "window.messages.length"


@pytest.fixture(scope="module")
def framing_server(e2e_server: RunningServer, tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    yield from serve_on_the_frame_site(e2e_server, tmp_path_factory.mktemp("call-greeting"), call_origin=CALL_ORIGIN)


@contextmanager
def in_the_greeting_call(
    visitor: Page, browser_coverage: BrowserCoverage, server: RunningServer, address: str, *, greets: bool = False
) -> Generator[Frame]:
    page = greeting_page_holding(address, server.base_url, greets_every_ready=greets)
    with served_from(CALL_ORIGIN, visitor, browser_coverage, page):
        visitor.goto(f"{CALL_ORIGIN}/")
        handle = visitor.locator(FRAME).element_handle()
        frame = handle.content_frame()
        assert frame is not None
        yield frame


def messages_of_the_frame(visitor: Page) -> list[Any]:
    return visitor.evaluate("window.messages")


def wait_for_ready(visitor: Page) -> None:
    visitor.wait_for_function(f"{RECORDED_MESSAGES} >= 1")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_valid_hello_drops_the_bar_and_the_table_plays_on(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server, **form_factor)

    with in_the_greeting_call(visitor, browser_coverage, framing_server, table_url(framing_server, path), greets=True):
        table = visitor.frame_locator(FRAME)

        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)
        expect(table.locator(BAR)).to_have_count(0)


def test_a_call_that_never_greets_leaves_the_bar(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server)

    with in_the_greeting_call(visitor, browser_coverage, framing_server, table_url(framing_server, path)):
        wait_for_ready(visitor)
        table = visitor.frame_locator(FRAME)

        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)
        expect(table.locator(BAR)).to_be_visible()


def test_the_frame_posts_exactly_one_ready_naming_its_own_table_to_the_call_origin(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server)

    with in_the_greeting_call(visitor, browser_coverage, framing_server, table_url(framing_server, path)):
        wait_for_ready(visitor)
        expect(visitor.frame_locator(FRAME).locator(CHAIR)).to_have_count(THREE_CHAIRS)

        assert messages_of_the_frame(visitor) == [{"v": 1, "type": "ready", "table": table_id_of(path)}]


def add_sibling(visitor: Page, name: str, attributes: str) -> Frame:
    visitor.evaluate(
        """([name, attributes]) => new Promise((resolve) => {
            document.body.insertAdjacentHTML("beforeend", `<iframe name="${name}" ${attributes}></iframe>`);
            document.querySelector(`iframe[name="${name}"]`).addEventListener("load", resolve);
        })""",
        [name, attributes],
    )
    frame = visitor.frame(name=name)
    assert frame is not None
    return frame


def sender_from_the_call(visitor: Page) -> Callable[[Any, int], None]:
    return lambda data, marker: visitor.evaluate(
        "([data, marker]) => { sendToStage(data); sendToStage({ marker }); }", [data, marker]
    )


def sender_from_a_sibling(sibling: Frame) -> Callable[[Any, int], None]:
    return lambda data, marker: sibling.evaluate(
        """([data, marker]) => {
            const stage = parent.frames[0];
            stage.postMessage(data, "*");
            stage.postMessage({ marker }, "*");
        }""",
        [data, marker],
    )


BAD_MESSAGES = [
    pytest.param("a sibling on another origin", VALID_HELLO, id="sibling-on-another-origin"),
    pytest.param("a sibling on the call origin", VALID_HELLO, id="sibling-on-the-call-origin"),
    pytest.param("the call", "hello", id="a-string"),
    pytest.param("the call", {**VALID_HELLO, "extra": "x" * MEGABYTE}, id="a-megabyte-field"),
    pytest.param("the call", {**VALID_HELLO, "v": 2}, id="version-2"),
]


@pytest.mark.parametrize(("sender", "data"), BAD_MESSAGES)
def test_a_message_that_fails_a_check_leaves_the_bar_until_the_valid_hello_comes(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    sender: str,
    data: Any,
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server)

    with ExitStack() as stack:
        skat = stack.enter_context(
            in_the_greeting_call(visitor, browser_coverage, framing_server, table_url(framing_server, path))
        )
        stack.enter_context(served_from(OTHER_ORIGIN, visitor, browser_coverage, "<!doctype html><title>other</title>"))
        wait_for_ready(visitor)
        table = visitor.frame_locator(FRAME)
        expect(table.locator(CHAIR)).to_have_count(THREE_CHAIRS)
        skat.evaluate(
            """() => {
                window.markers = [];
                addEventListener("message", (event) => {
                    if (event.data?.marker !== undefined) markers.push(event.data.marker);
                });
            }"""
        )
        if sender == "the call":
            send = sender_from_the_call(visitor)
        elif sender == "a sibling on another origin":
            send = sender_from_a_sibling(add_sibling(visitor, "other", f'src="{OTHER_ORIGIN}/"'))
        else:
            send = sender_from_a_sibling(add_sibling(visitor, "same", 'srcdoc=""'))
        marker = 1

        send(data, marker)
        skat.wait_for_function("marker => markers.includes(marker)", arg=marker)
        expect(table.locator(BAR)).to_be_visible()
        visitor.evaluate("greet()")

        expect(table.locator(BAR)).to_have_count(0)


@pytest.mark.parametrize("reduced_motion", ["no-preference", "reduce"])
def test_a_tap_at_the_moment_the_bar_drops_seats_nobody_and_a_tap_after_it_seats_the_visitor(
    open_person: Callable[..., Page],
    browser_coverage: BrowserCoverage,
    framing_server: RunningServer,
    reduced_motion: str,
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server, username="ben", reduced_motion=reduced_motion)

    with in_the_greeting_call(visitor, browser_coverage, framing_server, table_url(framing_server, path)):
        visitor.evaluate(
            "document.getElementById('stage').style.cssText = 'position:fixed;inset:0;width:100%;height:100%;border:0'"
        )
        wait_for_ready(visitor)
        table = visitor.frame_locator(FRAME)
        expect(table.get_by_role("button", name=SIT_DOWN)).to_have_count(THREE_CHAIRS - 1)

        visitor.evaluate("greet()")
        expect(table.locator(BAR)).to_have_count(0)
        box = table.locator(".chair[data-seat='2']").get_by_role("button", name=SIT_DOWN).bounding_box()
        assert box is not None
        visitor.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        table.locator(".chair[data-seat='3']").get_by_role("button", name=SIT_DOWN).click()

        expect(table.locator(".chair[data-seat='3'] .plate")).to_have_text(YOU)
        expect(table.locator(".chair[data-seat='2'] .plate")).to_have_text(SEAT_FREE)


def test_a_reloaded_frame_greets_again(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server)

    with in_the_greeting_call(
        visitor, browser_coverage, framing_server, table_url(framing_server, path), greets=True
    ) as skat:
        table = visitor.frame_locator(FRAME)
        expect(table.locator(BAR)).to_have_count(0)

        skat.evaluate("location.reload()")
        visitor.wait_for_function(f"{RECORDED_MESSAGES} >= 2")

        expect(table.locator(BAR)).to_have_count(0)
        assert len(messages_of_the_frame(visitor)) == 2


@pytest.mark.parametrize("search", ["", "?mode=call"], ids=["without-the-marker", "with-the-marker"])
def test_a_top_level_table_page_posts_nothing_and_keeps_its_bar(
    open_person: Callable[..., Page], framing_server: RunningServer, search: str
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server)
    requests: list[str] = []
    visitor.on("request", lambda request: requests.append(request.url))

    visitor.goto(f"{framing_server.base_url}{path}{search}")

    expect(visitor.locator(CHAIR)).to_have_count(THREE_CHAIRS)
    expect(visitor.locator(BAR)).to_be_visible()
    assert [url for url in requests if CALL_ORIGIN_PATH in url] == []


def test_a_framed_table_page_without_the_marker_posts_nothing_and_asks_for_no_origin(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server)
    requests: list[str] = []
    visitor.on("request", lambda request: requests.append(request.url))

    with in_the_greeting_call(visitor, browser_coverage, framing_server, f"{framing_server.base_url}{path}"):
        expect(visitor.frame_locator(FRAME).locator(CHAIR)).to_have_count(THREE_CHAIRS)

        assert messages_of_the_frame(visitor) == []
        assert [url for url in requests if CALL_ORIGIN_PATH in url] == []


def test_the_call_sign_in_face_posts_nothing(
    open_person: Callable[..., Page], browser_coverage: BrowserCoverage, framing_server: RunningServer
) -> None:
    path = new_table(open_person, framing_server)
    visitor = open_person(server=framing_server, signed_in=False)

    with in_the_greeting_call(visitor, browser_coverage, framing_server, table_url(framing_server, path)):
        expect(visitor.frame_locator(FRAME).get_by_role("link", name=LOG_IN, exact=True)).to_be_visible()

        assert messages_of_the_frame(visitor) == []
