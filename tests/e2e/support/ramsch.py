import itertools
import json
from typing import TYPE_CHECKING, Any, ClassVar

from playwright.sync_api import Page, expect

from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschScoring
from skat.table.records import SERIES_LENGTH_MIN, RamschOccasion
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import AddressedSession
from tests.e2e.support.tables import sit_in, watch

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

RAMSCH_OPTIONS = {
    "occasion": RamschOccasion.PASSED_IN,
    "scoring": RamschScoring.POINTS,
    "jungfrau": JungfrauRule.DOUBLES_LOSER,
    "durchmarsch": DurchmarschRule.WINS_120,
}
PASSING_ORDER = ("middlehand", "rearhand", "forehand")
command_numbers = itertools.count(1)


class RamschTable:
    """Three people at a table that plays Ramsch for a hand all pass, and a watcher; every step goes through the API."""

    options: ClassVar[dict[str, Any]] = {"ramsch": RAMSCH_OPTIONS}

    def __init__(
        self,
        open_person: Callable[..., Page],
        server: RunningServer,
        member_of: Callable[[Page], SeededMember],
        page_errors: list[str],
        form_factor: dict[str, Any],
    ) -> None:
        people = {
            username: record_page_errors(open_person(username=username, **form_factor), page_errors)
            for username in ("anna", "ben", "cleo", "dora")
        }
        sessions = [AddressedSession(server, member_of(person)) for person in people.values()]
        opened = json.loads(
            sessions[0].post(
                TABLES_PATH,
                {
                    "command_id": self._command_id(),
                    "series_length": SERIES_LENGTH_MIN,
                    "options": self.options,
                },
            )
        )
        self.api_path = f"{TABLES_PATH}/{opened['id']}"
        path = f"{TABLE_PAGE_PREFIX}{opened['id']}"
        for person in people.values():
            watch(person, server, path)
        for seat, username in ((2, "ben"), (3, "cleo")):
            sit_in(people[username], seat)
        self.sessions = dict(enumerate(sessions[:3], start=1))
        self.pages = dict(enumerate(list(people.values())[:3], start=1))
        self.watcher = people["dora"]
        self.everyone = list(people.values())
        expect(self.watcher.locator(".mark.pos")).to_have_count(3)
        chairs = self.view(1)["chairs"]
        self.names = {chair["seat"]: chair["occupant_name"] for chair in chairs}
        self.seat_at = {chair["hand"]["position"]: chair["seat"] for chair in chairs}

    @staticmethod
    def _command_id() -> str:
        return f"ramsch-result-{next(command_numbers):04d}"

    def view(self, seat: int) -> dict[str, Any]:
        return json.loads(self.sessions[seat].get(self.api_path))

    def pass_all(self) -> None:
        """The three seats pass in the order of the hand dealt now, whose positions turn with each dealer."""
        positions = {chair["hand"]["position"]: chair["seat"] for chair in self.view(1)["chairs"]}
        for position in PASSING_ORDER:
            seat = positions[position]
            self.sessions[seat].post(
                f"{self.api_path}{TABLE_AUCTION_PASS_SUFFIX}",
                {"command_id": self._command_id(), "version": self.view(seat)["version"]},
            )

    def ready_all(self) -> None:
        """„Weiter“ of every seat for the result its own view shows."""
        for seat, session in self.sessions.items():
            view = self.view(seat)
            body = {
                "command_id": self._command_id(),
                "ordinal": view["result"]["ordinal"],
                "series": view["series"]["number"],
            }
            session.post(f"{self.api_path}{TABLE_READY_SUFFIX}", body)

    def play_out(self) -> None:
        """Each seat on turn plays its first legal card until the last card of the tenth trick ends the Ramsch."""
        seat = self.view(1)["hand"]["playing"]["turn_seat"]
        while True:
            view = self.view(seat)
            card = min((card["suit"], card["rank"]) for card in view["hand"]["playing"]["legal_cards"])
            hand = json.loads(
                self.sessions[seat].post(
                    f"{self.api_path}{TABLE_CARD_SUFFIX}",
                    {
                        "command_id": self._command_id(),
                        "version": view["version"],
                        "suit": card[0],
                        "rank": card[1],
                    },
                )
            )["hand"]
            if hand is None:
                return
            seat = hand["playing"]["turn_seat"]

    def result(self) -> dict[str, Any]:
        return self.view(1)["result"]
