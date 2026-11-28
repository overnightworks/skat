"""The table waits for a seat that stays silent: after a minute every seated player but the awaited one is offered a
bell at its chair, and a tap rings a cowbell at that chair on every page and lets its person grumble, while the nudged
person also reads a sentence of who nudged.
"""

import re
import time
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.table.asking import ASK_AGAIN_AFTER
from skat.table.nudging import NudgeRefusal
from skat.web.nudging import TABLE_NUDGE_SUFFIX
from skat.web.playing import TABLE_GIVE_UP_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, WORDS, text
from tests.e2e.support.declaring import reload_and_wait
from tests.e2e.support.early_end import COMMAND_FAILED, NOTICE
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.server import skat_on_new_database
from tests.e2e.support.tables import chair_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

MILLISECONDS_PER_SECOND = 1000
REFUSED = 409
NUDGED = text(SOURCE_LANGUAGE, "table.nudged")
# Any of the lines a nudged chair grumbles.
ANY_GRUMBLE = re.compile(
    "|".join(re.escape(text(SOURCE_LANGUAGE, key)) for key in WORDS[SOURCE_LANGUAGE] if key.startswith("voice.grumble"))
)
# The cowbell and the grumble are gone within this many seconds.
COWBELL_STAYS_SECONDS = 10


class WaitedClock:
    """The server's clock, which a test moves forward to let the minute pass without waiting for it."""

    def __init__(self) -> None:
        self._passed = 0.0

    def __call__(self) -> float:
        return time.monotonic() + self._passed

    def pass_seconds(self, seconds: float) -> None:
        self._passed += seconds


def nudge_label(name: str) -> str:
    return f"{name} {text(SOURCE_LANGUAGE, 'table.nudge')}"


def nudges_you(name: str) -> str:
    return f"{name} {text(SOURCE_LANGUAGE, 'table.nudgesYou')}"


def cowbells(scope: Page | Locator) -> Locator:
    return scope.get_by_role("img", name=NUDGED)


def grumbles(scope: Page | Locator) -> Locator:
    return scope.get_by_text(ANY_GRUMBLE)


@pytest.fixture
def server_clock() -> WaitedClock:
    return WaitedClock()


@pytest.fixture
def e2e_server(tmp_path_factory: pytest.TempPathFactory, server_clock: WaitedClock) -> Iterator[RunningServer]:
    """A Skat of its own for each test, whose waits follow the test's clock."""
    with skat_on_new_database(tmp_path_factory, chair_clock=server_clock) as server:
        yield server


class SilentSeat:
    """A game in play whose forehand is on turn and stays silent: its two table mates may nudge it, a watcher not."""

    def __init__(self, table: PlayingTable, server_clock: WaitedClock) -> None:
        self.table = table
        self._server_clock = server_clock
        self.seat = table.seat_at["forehand"]
        self.name = table.names[self.seat]
        self.awaited = table.pages[self.seat]
        self.nudgers = [page for seat, page in table.pages.items() if seat != self.seat]
        self.watcher = table.watcher
        # The pages count the minute on a clock the test moves; a page opened again counts it from its own start.
        for page in table.everyone:
            page.clock.install()
            reload_and_wait(page)

    def chair(self, page: Page) -> Locator:
        return chair_of(page, self.seat)

    def hold_the_pages_still(self) -> None:
        """Stops the pages' clocks, so a timer fires only when the test lets the pages wait."""
        for page in self.table.everyone:
            page.clock.pause_at(page.evaluate("Date.now()") + MILLISECONDS_PER_SECOND)

    def let_the_pages_wait(self, seconds: float) -> None:
        for page in self.table.everyone:
            page.clock.fast_forward(int(seconds * MILLISECONDS_PER_SECOND))

    def let_the_server_wait(self, seconds: float) -> None:
        self._server_clock.pass_seconds(seconds)

    def bell_button(self, page: Page) -> Locator:
        return page.get_by_role("button", name=nudge_label(self.name))


@pytest.fixture
def silent_seat(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    server_clock: WaitedClock,
) -> Callable[..., SilentSeat]:
    def deal(form_factor: dict[str, Any], *, console: bool = True) -> SilentSeat:
        table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, console=console)
        return SilentSeat(table, server_clock)

    return deal


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_bell_comes_after_a_minute_to_the_seated_but_the_awaited_and_a_tap_rings_a_cowbell_for_everyone(
    silent_seat: Callable[..., SilentSeat], form_factor: dict[str, Any]
) -> None:
    waiting = silent_seat(form_factor)
    nudger = waiting.nudgers[0]
    nudger_name = waiting.table.names[waiting.table.seat_of(nudger)]
    for page in waiting.table.everyone:
        expect(waiting.bell_button(page)).to_have_count(0)
    waiting.let_the_pages_wait(ASK_AGAIN_AFTER / 2)
    expect(waiting.bell_button(nudger)).to_have_count(0)

    waiting.let_the_server_wait(ASK_AGAIN_AFTER)
    waiting.let_the_pages_wait(ASK_AGAIN_AFTER / 2)

    for page in waiting.nudgers:
        expect(waiting.bell_button(page)).to_have_count(1)
    expect(waiting.bell_button(waiting.awaited)).to_have_count(0)
    expect(waiting.bell_button(waiting.watcher)).to_have_count(0)

    waiting.hold_the_pages_still()
    waiting.bell_button(nudger).click()

    for page in waiting.table.everyone:
        expect(cowbells(waiting.chair(page))).to_have_count(1)
        expect(grumbles(waiting.chair(page))).to_have_count(1)
    expect(waiting.bell_button(nudger)).to_have_count(0)
    expect(waiting.awaited.locator(NOTICE)).to_contain_text(nudges_you(nudger_name))
    assert len({grumbles(waiting.chair(page)).inner_text() for page in waiting.table.everyone}) == 1
    for page in (*waiting.nudgers, waiting.watcher):
        expect(page.locator(NOTICE)).to_have_count(0)

    waiting.let_the_pages_wait(COWBELL_STAYS_SECONDS)

    for page in waiting.table.everyone:
        expect(cowbells(page)).to_have_count(0)
        expect(grumbles(page)).to_have_count(0)


def test_a_new_version_at_the_same_awaited_chair_starts_the_minute_again(
    silent_seat: Callable[..., SilentSeat],
) -> None:
    waiting = silent_seat(PHONE)
    declarer = waiting.table.pages[waiting.table.declarer_seat]
    waiting.let_the_server_wait(ASK_AGAIN_AFTER)
    waiting.let_the_pages_wait(ASK_AGAIN_AFTER + 1)
    expect(waiting.bell_button(declarer)).to_have_count(1)

    # The declarer asks the defenders to let him give up: the new version still waits for the same chair.
    waiting.table.declaring.step(waiting.table.declarer_seat, TABLE_GIVE_UP_SUFFIX)
    expect(waiting.bell_button(declarer)).to_have_count(0)
    waiting.let_the_server_wait(ASK_AGAIN_AFTER)
    waiting.let_the_pages_wait(2)

    expect(waiting.bell_button(declarer)).to_have_count(0)
    waiting.let_the_pages_wait(ASK_AGAIN_AFTER)
    expect(waiting.bell_button(declarer)).to_have_count(1)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_notice_and_the_cowbell_do_not_come_again_when_the_nudged_person_reloads(
    silent_seat: Callable[..., SilentSeat], form_factor: dict[str, Any]
) -> None:
    waiting = silent_seat(form_factor)
    waiting.let_the_server_wait(ASK_AGAIN_AFTER)
    waiting.let_the_pages_wait(ASK_AGAIN_AFTER + 1)
    waiting.bell_button(waiting.nudgers[0]).click()
    expect(waiting.awaited.locator(NOTICE)).to_have_count(1)

    reload_and_wait(waiting.awaited)

    expect(waiting.awaited.locator(NOTICE)).to_have_count(0)
    expect(cowbells(waiting.awaited)).to_have_count(0)
    expect(grumbles(waiting.awaited)).to_have_count(0)


def test_a_tap_the_server_refuses_as_too_early_changes_nothing_on_the_page(
    silent_seat: Callable[..., SilentSeat],
) -> None:
    # The browser logs the refusal it was sent as a failed resource, which is the answer under test.
    waiting = silent_seat(PHONE, console=False)
    nudger = waiting.nudgers[0]
    waiting.let_the_pages_wait(ASK_AGAIN_AFTER + 1)
    expect(waiting.bell_button(nudger)).to_have_count(1)

    with nudger.expect_response(lambda response: response.url.endswith(TABLE_NUDGE_SUFFIX)) as refused:
        waiting.bell_button(nudger).click()

    assert refused.value.status == REFUSED
    assert refused.value.json()["reason"] == NudgeRefusal.TOO_EARLY
    expect(waiting.bell_button(nudger)).to_have_count(1)
    expect(cowbells(nudger)).to_have_count(0)
    expect(nudger.get_by_role("status").filter(has_text=COMMAND_FAILED)).to_have_count(0)
    expect(waiting.awaited.locator(NOTICE)).to_have_count(0)
