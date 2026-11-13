import itertools
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from playwright.sync_api import Locator, Page, expect

from skat.engine.bidding import VALID_BIDS
from skat.store.tables import PostgresTableTransactions
from skat.table.records import TableId
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.declaring import (
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
)
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.tables import open_new_table, sit_in, table_id_of, watch
from tests.support.payload_cards import wire_cards
from tests.support.played_game import after_a_game

if TYPE_CHECKING:
    from collections.abc import Callable

    from skat.table.game_list import ListEntry
    from skat.table.records import TableRecord
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

TAKE_SKAT = text(SOURCE_LANGUAGE, "declare.takeSkat")
command_numbers = itertools.count(1)
DECLARING_STEP_SUFFIXES = {
    "take": TABLE_DECLARING_TAKE_SUFFIX,
    "put_back": TABLE_DECLARING_PUT_BACK_SUFFIX,
    "declare": TABLE_DECLARING_DECLARE_SUFFIX,
}


def button_of(person: Page, name: str) -> Locator:
    return person.get_by_role("button", name=name, exact=True)


def reload_and_wait(person: Page) -> None:
    person.reload()
    expect(person.locator(".chair")).to_have_count(3)


class DeclaringTable:
    """A dealt table: three browsers at their chairs, one watching, and the declarer known by API, not by the page."""

    def __init__(
        self,
        open_person: Callable[..., Page],
        server: RunningServer,
        member_of: Callable[[Page], SeededMember],
        page_errors: list[str],
        form_factor: dict[str, Any],
        *,
        console: bool = True,
        hold_the_others_clock: bool = False,
        joiners: tuple[str, str] = ("ben", "cleo"),
    ) -> None:
        self.server = server
        opener = self._person(open_person, "anna", page_errors, form_factor, console)
        path = self._open_table(opener, server, member_of)
        self.table_id = table_id_of(path)
        self.api_path = f"{TABLES_PATH}/{self.table_id}"
        people = {1: opener}
        for seat, username in zip((2, 3), joiners, strict=True):
            person = self._person(open_person, username, page_errors, form_factor, console)
            watch(person, server, path)
            sit_in(person, seat)
            people[seat] = person
        self.watcher = self._person(open_person, "dora", page_errors, form_factor, console)
        watch(self.watcher, server, path)
        self.sessions = {seat: RawSession(server, member_of(person)) for seat, person in people.items()}
        chairs = json.loads(self.sessions[1].get(self.api_path))["chairs"]
        seat_at = {chair["hand"]["position"]: chair["seat"] for chair in chairs}
        self.declarer_seat = seat_at["middlehand"]
        self.declarer = people[self.declarer_seat]
        self.others = [person for seat, person in people.items() if seat != self.declarer_seat]
        if hold_the_others_clock:
            self._hold_the_clock_of(*self.others, self.watcher)
        self._win_the_auction(seat_at)
        expect(self.declarer.get_by_role("button", name=TAKE_SKAT)).to_be_visible()

    @staticmethod
    def _open_table(opener: Page, server: RunningServer, member_of: Callable[[Page], SeededMember]) -> str:
        """Opens the table through the page, which plays the official rules."""
        del member_of
        return open_new_table(opener, server)

    @staticmethod
    def _person(
        open_person: Callable[..., Page],
        username: str,
        page_errors: list[str],
        form_factor: dict[str, Any],
        console: bool,
    ) -> Page:
        return record_page_errors(open_person(username=username, **form_factor), page_errors, console=console)

    @staticmethod
    def _hold_the_clock_of(*people: Page) -> None:
        """Stops the page's timers, so the moment the auction ends lasts until the test lets time run.

        A fixed time keeps the page's clock on one moment while timers run, so pausing at that moment never
        lies in the past, however long the browser takes between the two calls.
        """
        stopped_at = datetime.now(UTC)
        for person in people:
            person.clock.set_fixed_time(stopped_at)
            person.clock.pause_at(stopped_at)

    def _win_the_auction(self, seat_at: dict[str, int]) -> None:
        """The middlehand holds the highest bid there is, so any game the page declares lies below it."""
        self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=VALID_BIDS[-1])
        self.step(seat_at["forehand"], TABLE_AUCTION_PASS_SUFFIX)
        self.step(seat_at["rearhand"], TABLE_AUCTION_PASS_SUFFIX)

    def step(self, seat: int, suffix: str, **fields: object) -> None:
        session = self.sessions[seat]
        version = json.loads(session.get(self.api_path))["version"]
        session.post(
            f"{self.api_path}{suffix}",
            {"command_id": f"declaring-step-{next(command_numbers):04d}", "version": version, **fields},
        )

    def declare_through_the_api(self, *, action: str, **fields: object) -> None:
        self.step(self.declarer_seat, DECLARING_STEP_SUFFIXES[action], **fields)

    def stored(self) -> TableRecord:
        with PostgresTableTransactions(self.server.engine).begin() as transaction:
            stored = transaction.table(TableId(self.table_id))
        assert stored is not None
        return stored

    def list_the_game(self, entry: ListEntry) -> None:
        """Ends the running hand with `entry` as its game, through the store, and reloads every page on its result."""
        with PostgresTableTransactions(self.server.engine).begin() as transaction:
            transaction.save_table(after_a_game(self.stored(), entry), played_at=None)
        for person in (self.declarer, *self.others, self.watcher):
            reload_and_wait(person)

    def result_as_sent(self, seat: int) -> dict[str, Any]:
        return json.loads(self.sessions[seat].get(self.api_path))["result"]

    def skat(self) -> set[tuple[str, str]]:
        stored = self.stored().hand
        assert stored is not None
        return wire_cards(stored.skat)

    def declaring_as_the_declarer_sees_it(self) -> dict[str, Any]:
        return json.loads(self.sessions[self.declarer_seat].get(self.api_path))["hand"]["declaring"]

    def name_of_the_declarer(self) -> str:
        chairs = json.loads(self.sessions[self.declarer_seat].get(self.api_path))["chairs"]
        return next(chair["occupant_name"] for chair in chairs if chair["seat"] == self.declarer_seat)

    def bid_value(self) -> int:
        return json.loads(self.sessions[self.declarer_seat].get(self.api_path))["hand"]["auction"]["declared"]["value"]
