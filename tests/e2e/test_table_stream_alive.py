import json
import time
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.e2e.support.edge import BehindEdge, skat_behind_an_edge
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.tables import open_new_table, watch
from tests.e2e.support.words import catalog_text

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

RECONNECTING = catalog_text("reconnecting")
HEARTBEAT_SECONDS = 1.0
IDLE_CUT_SECONDS = 3.0
IDLE_CUT_PERIODS = 10
# The edge answers 502 while Skat is down; the page's own retries reach Skat again within this wait.
EDGE_ANSWERED_SECONDS = 30
POLL_SECONDS = 0.1
BACK_SECONDS = 30_000
# Records on the page whether the reconnecting line has been shown since the page started watching. The line
# stays in the page and only its `hidden` attribute changes, so the watch follows that attribute.
WATCH_FOR_RECONNECTING = f"""() => {{
    window.reconnectingSeen = false;
    const check = () => {{
        for (const line of document.querySelectorAll('[role="status"]')) {{
            if (!line.hidden && line.textContent.includes({json.dumps(RECONNECTING)})) window.reconnectingSeen = true;
        }}
    }};
    new MutationObserver(check).observe(document.body, {{
        subtree: true,
        childList: true,
        characterData: true,
        attributes: true,
        attributeFilter: ["hidden"],
    }});
    check();
}}"""


@pytest.fixture
def behind_edge(tmp_path_factory: pytest.TempPathFactory) -> Iterator[BehindEdge]:
    """A Skat that beats its stream every second behind an edge that cuts a silence of three seconds."""
    with skat_behind_an_edge(
        tmp_path_factory, heartbeat_seconds=HEARTBEAT_SECONDS, idle_cut_seconds=IDLE_CUT_SECONDS
    ) as behind:
        yield behind


@pytest.fixture
def e2e_server(behind_edge: BehindEdge) -> RunningServer:
    return behind_edge.server


def is_table_stream(url: str) -> bool:
    return TABLES_PATH in url and url.endswith(TABLE_EVENTS_SUFFIX)


def reconnecting_line(page: Page):
    return page.get_by_role("status").filter(has_text=RECONNECTING)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_idle_table_never_shows_reconnecting_though_the_edge_cuts_silent_streams(
    open_person: Callable[..., Page],
    behind_edge: BehindEdge,
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
) -> None:
    server = behind_edge.server
    expected_request_failures.append(f"{server.base_url}{TABLES_PATH}/")
    person = open_person(server=server, **form_factor)
    path = open_new_table(person, server)
    watcher = open_person(server=server, **form_factor)
    stream_opens: list[str] = []
    watcher.on("request", lambda request: stream_opens.append(request.url) if is_table_stream(request.url) else None)
    watch(watcher, server, path)
    watcher.evaluate(WATCH_FOR_RECONNECTING)

    watcher.wait_for_timeout(IDLE_CUT_PERIODS * IDLE_CUT_SECONDS * 1000)

    assert watcher.evaluate("window.reconnectingSeen") is False
    assert len(stream_opens) == 1


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_page_that_met_a_502_while_skat_was_down_reconnects_by_itself(
    open_person: Callable[..., Page],
    behind_edge: BehindEdge,
    expected_request_failures: list[str],
    form_factor: dict[str, Any],
) -> None:
    server = behind_edge.server
    expected_request_failures.append(f"{server.base_url}{TABLES_PATH}/")
    person = open_person(server=server, **form_factor)
    open_new_table(person, server)
    person.evaluate("window.sameDocument = true")

    server.stop()
    deadline = time.monotonic() + EDGE_ANSWERED_SECONDS
    while behind_edge.edge.bad_gateways == 0 and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
    assert behind_edge.edge.bad_gateways >= 1, "the edge answered no 502 while Skat was down"
    expect(reconnecting_line(person)).to_be_visible(timeout=BACK_SECONDS)
    server.start()

    expect(reconnecting_line(person)).to_have_count(0, timeout=BACK_SECONDS)
    assert person.evaluate("window.sameDocument") is True
    expect(person.locator(".stage.stale")).to_have_count(0)
