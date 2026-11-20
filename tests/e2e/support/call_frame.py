"""A call page around a Skat table, as hopin's page frames it, and Skat served on the site they share."""

import json
import struct
import zlib
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from skat.web.constants import CALL_MODE, MODE_QUERY_NAME
from tests.e2e.support.server import loopback_sign_in, running_skat
from tests.e2e.support.tables import open_new_table

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from playwright.sync_api import Frame, FrameLocator, Page, Route

    from tests.e2e.support.browser_coverage import BrowserCoverage
    from tests.e2e.support.server import RunningServer

# One site, as hopin and Skat share one in production: a frame of another site gets no session cookie.
SKAT_HOST = "skat.frame.localhost"
CALL_HOST = "call.frame.localhost"
OTHER_HOST = "other.frame.localhost"
# Nothing listens on either port: the page routes answer the call host.
CALL_PORT = 8444
OTHER_PORT = CALL_PORT + 1
CALL_ORIGIN = f"https://{CALL_HOST}:{CALL_PORT}"
HTTP_OK = 200
# Chromium's console line for a frame its content security policy refused.
FRAME_REFUSED = "frame-ancestors"
# The attributes hopin's call page puts on the frame that holds a Skat table.
CALL_FRAME_ATTRIBUTES = (
    'sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox" '
    'allow="" referrerpolicy="no-referrer"'
)
FRAME = "#stage"
CHAIR = ".chair"
THREE_CHAIRS = 3


def serve_on_the_frame_site(
    e2e_server: RunningServer, directory: Path, **overrides: str | None
) -> Iterator[RunningServer]:
    loopback = loopback_sign_in(directory, SKAT_HOST, **overrides)
    tls = directory / "tls"
    tls.mkdir()
    with running_skat(loopback, tls, e2e_server.engine) as server:
        yield server


@contextmanager
def served_from(origin: str, page: Page, browser_coverage: BrowserCoverage, body: str) -> Iterator[None]:
    """Answer the page's navigations to `origin` with `body`; no server stands there."""

    def answer(route: Route) -> None:
        if not browser_coverage.cancel_take_reissue(route):
            route.fulfill(status=HTTP_OK, content_type="text/html", body=body)

    page.route(f"{origin}/**", answer)
    yield
    page.unroute(f"{origin}/**", answer)


def table_url(server: RunningServer, path: str) -> str:
    return f"{server.base_url}{path}?{MODE_QUERY_NAME}={CALL_MODE}"


def page_holding(frame_address: str, style: str = "") -> str:
    return (
        f'<!doctype html><title>call</title><iframe id="stage" src="{frame_address}" style="{style}" '
        f"{CALL_FRAME_ATTRIBUTES}></iframe>"
    )


# The greeting call page's script: it records what the Skat frame posts, greets a `ready` when asked, and lets a test
# send one message to the frame (`sendToStage`), the valid greeting (`greet`) or a `placed` for keys (`place`) itself.
# Like the call, it draws a stand-in video at the sent box of every placed key, under the transparent frame, and
# answers every `seats` with a `placed` of all its keys when `placeEverySeats` is set.
_GREETING_SCRIPT = """
window.messages = [];
window.greetEveryReady = GREET_EVERY_READY;
window.placeEverySeats = false;
window.placedKeys = [];
let tableId = null;
const stage = () => document.getElementById("stage").contentWindow;
window.sendToStage = (data) => stage().postMessage(data, SKAT_ORIGIN);
window.greet = () => sendToStage({ v: 1, type: "hello", attachment: 1, attempt: null });
window.lastSeats = () => messages.findLast((message) => message?.type === "seats") ?? null;
const redraw = () => {
    document.querySelectorAll(".stand-in").forEach((video) => video.remove());
    for (const seat of lastSeats()?.seats ?? []) {
        if (!placedKeys.includes(seat.key)) continue;
        const video = document.createElement("div");
        const { x, y, w, h } = seat.box;
        const { tl, tr, br, bl } = seat.radius ?? {};
        video.className = "stand-in";
        video.dataset.key = seat.key;
        const radius = seat.shape === "round" ? "50%" : `${tl}px ${tr}px ${br}px ${bl}px`;
        video.style.cssText = `position:fixed;z-index:0;background:rgb(255,0,255);left:${x}px;top:${y}px;`
            + `width:${w}px;height:${h}px;border-radius:${radius}`;
        document.body.append(video);
    }
};
window.place = (keys) => {
    placedKeys = keys;
    redraw();
    sendToStage({ v: 1, type: "placed", table: tableId, keys });
};
addEventListener("message", (event) => {
    if (event.source !== stage() || event.origin !== SKAT_ORIGIN) return;
    messages.push(event.data);
    if (event.data?.type === "ready") {
        tableId = event.data.table;
        if (greetEveryReady) greet();
    } else if (event.data?.type === "seats") {
        if (placeEverySeats) place(event.data.seats.map((seat) => seat.key));
        else redraw();
    }
});
"""

# Behind the transparent frame: a colour no part of the table has, so a pixel shows what lies under it.
BEHIND_THE_FRAME = "rgb(0, 200, 0)"
STAND_IN = (255, 0, 255)
_CALL_PAGE_STYLE = f"<style>html {{ color-scheme: dark; background: {BEHIND_THE_FRAME}; }}</style>"
FRAME_FILLING_THE_SCREEN = "position:fixed;inset:0;width:100%;height:100%;border:0;z-index:1;color-scheme:dark"


def greeting_page_holding(
    frame_address: str, skat_origin: str, *, greets_every_ready: bool = False, filling_the_screen: bool = False
) -> str:
    """The call page of `page_holding`, recording the frame's messages and greeting as the call page does."""
    script = _GREETING_SCRIPT.replace("SKAT_ORIGIN", json.dumps(skat_origin)).replace(
        "GREET_EVERY_READY", json.dumps(greets_every_ready)
    )
    style = FRAME_FILLING_THE_SCREEN if filling_the_screen else ""
    # A phone lays a page without this out 980 px wide, as the call's own page never does.
    viewport = '<meta name="viewport" content="width=device-width, initial-scale=1">'
    return viewport + page_holding(frame_address, style) + _CALL_PAGE_STYLE + f"<script>{script}</script>"


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


def sender_from_a_sibling(sibling: Frame) -> Callable[[Any, int], None]:
    return lambda data, marker: sibling.evaluate(
        """([data, marker]) => {
            const stage = parent.frames[0];
            stage.postMessage(data, "*");
            stage.postMessage({ marker }, "*");
        }""",
        [data, marker],
    )


def pixel_at(page: Page, x: float, y: float) -> tuple[int, int, int]:
    """The colour on screen at a point of the page, read from a one-pixel screenshot (an unfiltered 8-bit PNG)."""
    png = page.screenshot(clip={"x": x, "y": y, "width": 1, "height": 1})
    data = b"".join(_png_chunks(png, b"IDAT"))
    channels = 4 if png[25] == PNG_RGBA else 3
    raw = zlib.decompress(data)
    # One row of one pixel: whatever its filter, the first pixel's bytes are the colour.
    red, green, blue = raw[1], raw[2], raw[3]
    assert len(raw) == 1 + channels
    return red, green, blue


PNG_RGBA = 6


def _png_chunks(png: bytes, kind: bytes) -> Iterator[bytes]:
    position = len(PNG_SIGNATURE)
    while position < len(png):
        (length,) = struct.unpack(">I", png[position : position + 4])
        if png[position + 4 : position + 8] == kind:
            yield png[position + 8 : position + 8 + length]
        position += 12 + length


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def new_table(open_person: Callable[..., Page], server: RunningServer) -> str:
    return open_new_table(open_person(server=server), server)


# What the page's chairs draw, read in the frame: which marks lie in a tile's top-left quarter or under its position
# label, whether an own-seat bar shows its glass, whether any tile rim lies inside its box, and how the dashed
# agent rim lies against its box (the probe gives each tile the agent class).
_CHAIR_LOOK_PROBE = """chairs => {
    const overlaps = (mark, tile) => mark.right > tile.left && mark.left < tile.left + tile.width / 2
        && mark.bottom > tile.top && mark.top < tile.top + tile.height / 2;
    const look = {
        marks: 0, marksInTopLeftQuarter: 0, positionedMarks: 0, marksOverPositionLabel: 0, barPillsShown: 0,
        rimsInsideTile: 0, agentRimInsideTile: 0, mostMarksOnAChair: 0,
    };
    for (const chair of chairs) {
        const tile = chair.querySelector(".tile");
        if (!tile) continue;
        const box = tile.getBoundingClientRect();
        const label = chair.querySelector(".mark.pos");
        const labelBox = label && label.getBoundingClientRect();
        const pill = chair.querySelector(".bar-pill");
        if (pill && getComputedStyle(pill).display !== "none") look.barPillsShown += 1;
        const chairMarks = chair.querySelectorAll(".mark:not(.pos)");
        look.mostMarksOnAChair = Math.max(look.mostMarksOnAChair, chairMarks.length);
        for (const mark of chairMarks) {
            look.marks += 1;
            const at = mark.getBoundingClientRect();
            if (labelBox && at.right > labelBox.left && at.left < labelBox.right
                && at.bottom > labelBox.top && at.top < labelBox.bottom) look.marksOverPositionLabel += 1;
            if (overlaps(mark.getBoundingClientRect(), box)) look.marksInTopLeftQuarter += 1;
            if (getComputedStyle(mark).position === "absolute") look.positionedMarks += 1;
        }
        if (getComputedStyle(tile).boxShadow.includes("inset")) look.rimsInsideTile += 1;
        tile.classList.add("agent");
        const rim = getComputedStyle(tile, "::before");
        if (parseFloat(rim.top) + parseFloat(rim.borderTopWidth) > 0
            || parseFloat(rim.left) + parseFloat(rim.borderLeftWidth) > 0) look.agentRimInsideTile += 1;
        tile.classList.remove("agent");
    }
    return look;
}"""


def chair_look(scope: Page | FrameLocator) -> dict[str, int]:
    """Counts of the chairs' marks and rims as `_CHAIR_LOOK_PROBE` reads them in `scope`."""
    look: dict[str, int] = scope.locator(CHAIR).evaluate_all(_CHAIR_LOOK_PROBE)
    return look
