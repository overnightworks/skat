import itertools
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from playwright.sync_api import Page, expect

from skat.engine.bidding import VALID_BIDS
from skat.store.tables import PostgresTableTransactions
from skat.table.records import TableId
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.declaring import TABLE_DECLARATION_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.tables import open_new_table, sit_in, table_id_of, watch
from tests.e2e.support.words import catalog_text
from tests.support.payload_cards import wire_cards

if TYPE_CHECKING:
    from collections.abc import Callable

    from skat.table.records import TableRecord
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

TAKE_SKAT = catalog_text("takeSkat")
command_numbers = itertools.count(1)


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
        path = open_new_table(opener, server)
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
        """Stops the page's timers, so the moment the auction ends lasts until the test lets time run."""
        stopped_at = datetime.now(UTC) + timedelta(seconds=1)
        for person in people:
            person.clock.install(time=stopped_at)
            person.clock.pause_at(stopped_at + timedelta(seconds=1))

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

    def declare_through_the_api(self, **fields: object) -> None:
        self.step(self.declarer_seat, TABLE_DECLARATION_SUFFIX, **fields)

    def stored(self) -> TableRecord:
        with PostgresTableTransactions(self.server.engine).begin() as transaction:
            stored = transaction.table(TableId(self.table_id))
        assert stored is not None
        return stored

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
