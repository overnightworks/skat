"""The timeline of every page an end-to-end test opens, printed when the test fails.

A failing end-to-end test leaves its assertion and an aria snapshot, which say what the page showed and not what
happened before. The record lists, per page and in the browser's own time order, each request with its status
and end, each message of an event stream (its size only), each navigation of the main frame, each console
message and page error and the page's close, and renders the page's state at the moment of the failure.

Times come from the browser's events: the sync API hands them to the test thread only while it is inside a
Playwright call, so the moment the thread handled one says nothing about when it happened. A close, which the
browser sends no time with, takes the test thread's clock mapped onto the browser's.

It holds no header, no cookie value, no body and no stream data: a request line carries the method, the path and
the names of the query parameters, never their values.
"""

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError

from skat.web.words import SOURCE_LANGUAGE, text

if TYPE_CHECKING:
    from playwright.sync_api import CDPSession, Page

type CdpParameters = dict[str, Any]

DOCUMENT = "Document"
# The page's own files, which would bury the lines that matter; one that fails or is refused still gets its line.
ASSET_KINDS = frozenset({"Script", "Stylesheet", "Image", "Font", "Media"})
FIRST_ERROR_STATUS = 400
MILLISECONDS = 1000
CONSOLE_TEXT_LIMIT = 200
RECONNECTING = text(SOURCE_LANGUAGE, "table.reconnecting")
# What the page shows of its own at the moment of the failure; each answer is a word, never page content.
PAGE_STATE_SCRIPT = f"""() => {{
    const line = [...document.querySelectorAll('[role="status"]')]
        .find((element) => element.textContent.includes({json.dumps(RECONNECTING)}));
    const watchers = document.querySelector('.watchers span');
    return {{
        url: location.pathname + location.search.replace(/=[^&]*/g, ''),
        now: performance.now() / {MILLISECONDS},
        reconnecting: line === undefined ? 'absent' : line.hidden ? 'hidden' : 'shown',
        watchers: watchers === null ? 'none' : watchers.textContent,
    }};
}}"""


def printable(url: str) -> str:
    """The path and the names of the query parameters, which carry no value a log may not show."""
    parts = urlsplit(url)
    names = "&".join(pair.partition("=")[0] for pair in parts.query.split("&") if pair)
    return f"{parts.path}?{names}" if names else parts.path


@dataclass
class SentRequest:
    method: str
    path: str
    kind: str
    at: float

    @property
    def is_asset(self) -> bool:
        return self.kind in ASSET_KINDS


@dataclass
class PageTimeline:
    label: str
    page: Page
    session: CDPSession
    lines: list[tuple[float, str]] = field(default_factory=list)
    requests: dict[str, SentRequest] = field(default_factory=dict)
    main_frame: str = ""
    closed: bool = False


class FailureRecord:
    """Collects the timeline of each page it watches; `render` is the text a failure prints."""

    def __init__(self) -> None:
        self._timelines: list[PageTimeline] = []
        self._wall_clock_offset: float | None = None
        self._latest = 0.0

    def watch(self, page: Page, label: str) -> None:
        """Record this page from now on; the label is the person's name."""
        session = page.context.new_cdp_session(page)
        timeline = PageTimeline(label, page, session)
        timeline.main_frame = session.send("Page.getFrameTree")["frameTree"]["frame"]["id"]
        for event, handler in {
            "Network.requestWillBeSent": self._request,
            "Network.responseReceived": self._response,
            "Network.loadingFinished": self._finished,
            "Network.loadingFailed": self._failed,
            "Network.eventSourceMessageReceived": self._message,
            "Runtime.consoleAPICalled": self._console,
            "Runtime.exceptionThrown": self._exception,
            "Log.entryAdded": self._log_entry,
        }.items():
            session.on(event, lambda parameters, handler=handler: handler(timeline, parameters))
        session.send("Network.enable")
        session.send("Runtime.enable")
        session.send("Log.enable")
        page.on("close", lambda _: self._close(timeline))
        self._timelines.append(timeline)

    def render(self) -> str:
        """Every page's lines in time order, then its state now when it is still open."""
        base = min((at for timeline in self._timelines for at, _ in timeline.lines), default=0.0)
        sections = [self._section(timeline, base) for timeline in self._timelines]
        return "\n\n".join(sections)

    def _section(self, timeline: PageTimeline, base: float) -> str:
        lines = [f"== {timeline.label}"]
        lines += [f"+{at - base:.3f}s {line}" for at, line in sorted(timeline.lines, key=lambda entry: entry[0])]
        lines.append(f"state now: {self._state(timeline)}")
        return "\n".join(lines)

    def _state(self, timeline: PageTimeline) -> str:
        if timeline.closed:
            return "closed"
        try:
            state = timeline.page.evaluate(PAGE_STATE_SCRIPT)
        except PlaywrightError as error:
            return f"unreadable ({type(error).__name__})"
        return (
            f"url {state['url']}, performance.now() {state['now']:.3f}s, "
            f"reconnect line {state['reconnecting']}, watchers {state['watchers']}"
        )

    def _add(self, timeline: PageTimeline, at: float, line: str) -> None:
        self._latest = max(self._latest, at)
        timeline.lines.append((at, line))

    def _browser_time_of_wall_clock(self, seconds: float) -> float:
        return seconds - self._wall_clock_offset if self._wall_clock_offset is not None else self._latest

    def _request(self, timeline: PageTimeline, parameters: CdpParameters) -> None:
        if self._wall_clock_offset is None:
            self._wall_clock_offset = parameters["wallTime"] - parameters["timestamp"]
        request = parameters["request"]
        kind = parameters.get("type", "Other")
        sent = SentRequest(request["method"], printable(request["url"]), kind, parameters["timestamp"])
        timeline.requests[parameters["requestId"]] = sent
        if not sent.is_asset:
            navigates = kind == DOCUMENT and parameters.get("frameId") == timeline.main_frame
            self._add(timeline, sent.at, f"{'navigate' if navigates else 'request'} {sent.method} {sent.path} ({kind})")

    def _response(self, timeline: PageTimeline, parameters: CdpParameters) -> None:
        sent, at = self._later_of(timeline, parameters)
        status = parameters["response"]["status"]
        if not sent.is_asset or status >= FIRST_ERROR_STATUS:
            self._add(timeline, at, f"response {status} {sent.method} {sent.path}")

    def _finished(self, timeline: PageTimeline, parameters: CdpParameters) -> None:
        sent, at = self._later_of(timeline, parameters)
        if not sent.is_asset:
            self._add(timeline, at, f"finished {sent.method} {sent.path}")

    def _failed(self, timeline: PageTimeline, parameters: CdpParameters) -> None:
        sent, at = self._later_of(timeline, parameters)
        self._add(timeline, at, f"failed {sent.method} {sent.path}: {parameters['errorText']}")

    def _message(self, timeline: PageTimeline, parameters: CdpParameters) -> None:
        sent, at = self._later_of(timeline, parameters)
        self._add(timeline, at, f"message {sent.path} {len(parameters['data'].encode())} bytes")

    def _console(self, timeline: PageTimeline, parameters: CdpParameters) -> None:
        words = " ".join(str(argument.get("value", argument.get("description", ""))) for argument in parameters["args"])
        self._console_line(timeline, parameters["timestamp"], f"console.{parameters['type']}", words)

    def _log_entry(self, timeline: PageTimeline, parameters: CdpParameters) -> None:
        entry = parameters["entry"]
        # The browser's own report of a failed request carries the request's address, which its text leaves out.
        address = f" {printable(entry['url'])}" if "url" in entry else ""
        self._console_line(timeline, entry["timestamp"], f"log.{entry['level']}", entry["text"] + address)

    def _exception(self, timeline: PageTimeline, parameters: CdpParameters) -> None:
        details = parameters["exceptionDetails"]
        words = details.get("exception", {}).get("description", details["text"])
        self._console_line(timeline, parameters["timestamp"], "page error", words)

    def _console_line(self, timeline: PageTimeline, milliseconds: float, kind: str, words: str) -> None:
        at = self._browser_time_of_wall_clock(milliseconds / MILLISECONDS)
        self._add(timeline, at, f"{kind}: {words[:CONSOLE_TEXT_LIMIT]}")

    def _close(self, timeline: PageTimeline) -> None:
        timeline.closed = True
        self._add(timeline, self._browser_time_of_wall_clock(time.time()), "closed")

    @staticmethod
    def _later_of(timeline: PageTimeline, parameters: CdpParameters) -> tuple[SentRequest, float]:
        """The request an event belongs to and its time, never before the request's last event: the browser's
        stamps of one request can differ by less than the resolution of the record.
        """
        # A request sent before the page was watched has no line of its own.
        sent = timeline.requests.setdefault(
            parameters["requestId"], SentRequest("?", "?", "Other", parameters["timestamp"])
        )
        sent.at = max(sent.at, parameters["timestamp"])
        return sent, sent.at
