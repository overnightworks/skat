import itertools
import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschScoring
from skat.table.records import SERIES_LENGTH_MIN, RamschOccasion
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import AddressedSession
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.result_card import CARD, LOST, MINUS, WON, expect_the_page_around_the_card
from tests.e2e.support.tables import sit_in, watch

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

WEITER = text(SOURCE_LANGUAGE, "table.weiter")
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
                    "options": {"ramsch": RAMSCH_OPTIONS},
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
        for position in PASSING_ORDER:
            seat = self.seat_at[position]
            self.sessions[seat].post(
                f"{self.api_path}{TABLE_AUCTION_PASS_SUFFIX}",
                {"command_id": self._command_id(), "version": self.view(seat)["version"]},
            )

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


def signed(number: int) -> str:
    return f"{MINUS}{-number}" if number < 0 else f"+{number}"


def with_minus(number: int) -> str:
    return f"{MINUS}{-number}" if number < 0 else str(number)


def expected_head(table: RamschTable, result: dict[str, Any], seat: int | None) -> str:
    sweeper = result["durchmarsch_seat"]
    if sweeper is not None:
        return WON if seat == sweeper else text(SOURCE_LANGUAGE, "result.durchmarsch")
    losers = [each["seat"] for each in result["seats"] if each["score"] < 0]
    if seat in losers:
        return LOST
    names = f" {text(SOURCE_LANGUAGE, 'result.and')} ".join(table.names[loser] for loser in losers)
    key = "result.loses" if len(losers) == 1 else "result.losesTogether"
    return text(SOURCE_LANGUAGE, key, **{"name" if len(losers) == 1 else "names": names})


def expect_the_card(table: RamschTable) -> None:
    """Every viewer, a watcher included, reads the head, the eyes and the value of the answer, from their own side."""
    result = table.result()
    leader = next(
        each
        for each in result["seats"]
        if each["seat"] == result["durchmarsch_seat"] or (result["durchmarsch_seat"] is None and each["score"] < 0)
    )
    seats = {page: seat for seat, page in table.pages.items()}
    for person in table.everyone:
        card: Locator = person.locator(CARD)
        expect(card).to_have_count(1)
        expect(card.locator("h3")).to_have_text(expected_head(table, result, seats.get(person)))
        expect(card.locator(".sub")).to_have_text(text(SOURCE_LANGUAGE, "game.ramsch"))
        expect(card.locator(".eq")).to_have_text(text(SOURCE_LANGUAGE, "result.eyes", points=str(leader["points"])))
        expect(card.locator(".value")).to_have_text(signed(leader["score"]))
        expect(card.locator(".list span")).to_have_count(3)
        expect(card.locator(".reck")).to_have_count(3)
        for each in result["seats"]:
            expect(card.locator(f".reck[data-seat='{each['seat']}'] .dl")).to_have_text(
                signed(each["score"]) if each["score"] > 0 else with_minus(each["score"])
            )


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_everyone_reads_the_ramsch_result_card_and_weiter_works(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, form_factor)
    table.pass_all()
    table.play_out()

    expect_the_card(table)
    expect_the_page_around_the_card(table.everyone)
    table.pages[1].locator(".actions").get_by_role("button", name=WEITER).click()
    for person in table.everyone:
        expect(person.locator(".chair[data-seat='1'] .mark.ready")).to_have_count(1)
    assert page_errors == []
