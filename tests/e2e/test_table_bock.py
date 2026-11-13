import json
import re
import uuid
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from playwright.sync_api import Page, expect

from skat.engine.bidding import VALID_BIDS
from skat.engine.tricks import CARDS_IN_A_GAME
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.kontra import KONTRA_OPTIONS, say_kontra_as_an_opponent
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.ramsch import RAMSCH_OPTIONS, RamschTable
from tests.e2e.support.result_card import CARD, MINUS, TIMES, loosely, signed

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

BIDDING = text(SOURCE_LANGUAGE, "table.bidding")
PASSED_IN = text(SOURCE_LANGUAGE, "table.passedIn")
RULE_CHIP = ".rulepill .chip"
BOCK_WORD = text(SOURCE_LANGUAGE, "rules.chipBock")
BOCK_COUNT = f"{RULE_CHIP} .n"
BOCK_LINE = ".plaque .bock-line"
BOCK_FACTOR = f"{BOCK_LINE} b"


class BockTable(DeclaringTable):
    """A table whose Bock rounds start with a passed-in hand, opened through the API.

    The first hands are passed in, so the table has a Bock round before the first game: the middlehand of the hand dealt
    after them bids the lowest value and declares. `counts` holds the games to come after each passed-in hand.
    """

    hands_passed_in = 1
    overlap = "append"
    other_options: ClassVar[dict[str, Any]] = {}

    def _open_table(self, opener: Page, server: RunningServer, member_of: Callable[[Page], SeededMember]) -> str:
        del member_of
        options = {"bock": {"triggers": ["passed-in"], "overlap": self.overlap}, **self.other_options}
        answer = opener.request.post(
            f"{server.base_url}{TABLES_PATH}",
            data={"command_id": uuid.uuid4().hex, "series_length": 36, "options": options},
            headers={"Origin": server.base_url},
        )
        assert answer.ok, answer.text()
        path = f"{TABLE_PAGE_PREFIX}{answer.json()['id']}"
        opener.goto(f"{server.base_url}{path}")
        expect(opener.locator(".chair")).to_have_count(3)
        return path

    def _win_the_auction(self, seat_at: dict[str, int]) -> None:
        self.counts: list[int] = []
        for _ in range(self.hands_passed_in):
            for position in ("middlehand", "rearhand", "forehand"):
                self.step(seat_at[position], TABLE_AUCTION_PASS_SUFFIX)
            expect(self.watcher.locator(".plaque .verdict")).to_have_text(PASSED_IN)
            expect(self.watcher.locator(".plaque")).to_have_text(BIDDING)
            seat_at = self._seat_at()
            self.counts.append(self.bock()["games_left"])
        self._name_the_declarer(seat_at)
        self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=VALID_BIDS[0])
        self.step(seat_at["forehand"], TABLE_AUCTION_PASS_SUFFIX)
        self.step(seat_at["rearhand"], TABLE_AUCTION_PASS_SUFFIX)

    def bock(self) -> dict[str, int]:
        return json.loads(self.sessions[1].get(self.api_path))["bock"]


class KontraBockTable(BockTable):
    """A Bock round table whose opponents may also say Kontra."""

    other_options: ClassVar[dict[str, Any]] = {"kontra": KONTRA_OPTIONS}


class TwoPassedInBockTable(BockTable):
    """The second passed-in hand meets a pending round, which ignores its trigger, so it only uses up a game."""

    hands_passed_in = 2
    overlap = "ignore"


def expect_the_count(table: PlayingTable) -> None:
    """Every viewer, the watcher too, reads the answer's games to come on the chip."""
    left = table.view(table.declarer_seat)["bock"]["games_left"]
    for person in table.everyone:
        expect(person.locator(RULE_CHIP)).to_have_count(1)
        expect(person.locator(BOCK_COUNT)).to_have_text(str(left))
        expect(person.locator(BOCK_COUNT)).to_have_attribute(
            "aria-label", text(SOURCE_LANGUAGE, "rules.bockLeft", count=left)
        )


def expect_the_plaque_line(table: PlayingTable) -> None:
    factor = table.view(table.declarer_seat)["bock"]["factor"]
    for person in table.everyone:
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        expect(person.locator(BOCK_LINE)).to_have_text(text(SOURCE_LANGUAGE, "bock.factor", factor=str(factor)))
        expect(person.locator(BOCK_FACTOR)).to_have_text(text(SOURCE_LANGUAGE, "bock.times", factor=str(factor)))
        expect(person.locator(BOCK_FACTOR)).to_have_css("font-weight", "700")


def expect_the_chip_to_explain_the_score(table: PlayingTable) -> None:
    result = table.result()
    for person in table.everyone:
        card = person.locator(CARD)
        chip = text(SOURCE_LANGUAGE, "bock.factor", factor=str(result["bock_factor"]))
        expect(card.locator(".ladder > *")).to_have_count(len(result["levels"]) + 2)
        expect(card.locator(".ladder > *").last).to_have_text(chip)
        expect(card.locator(".eq")).to_have_text(
            loosely(str(result["multiplier"]), TIMES, str(result["base_value"]), "=", str(result["game_value"]))
        )
        expect(card.locator(".value")).to_have_text(re.compile(rf"^\s*[+{MINUS}]{abs(result['score'])}\s*$"))
        drawn = int(card.locator(".eq b").inner_text()) * result["bock_factor"] * (2 if result["doubled"] else 1)
        assert drawn == abs(result["score"])


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_every_viewer_reads_the_games_to_come_the_plaque_and_the_card_of_a_bock_game(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, declaring=BockTable)
    games_in_the_round = table.view(table.declarer_seat)["bock"]["games_left"]
    expect_the_count(table)
    expect_the_plaque_line(table)
    for person in table.everyone:
        person.reload()
        expect(person.locator(".chair")).to_have_count(3)
    expect_the_count(table)
    expect_the_plaque_line(table)

    table.play_out(CARDS_IN_A_GAME)

    expect_the_chip_to_explain_the_score(table)
    for seat in table.names:
        table.ready_through_the_api(seat)
    for person in table.everyone:
        expect(person.locator(CARD)).to_have_count(0)
    assert table.view(table.declarer_seat)["bock"]["games_left"] == games_in_the_round - 1
    expect_the_count(table)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", [pytest.param(PHONE, id="390")])
def test_a_passed_in_hand_in_a_bock_round_uses_up_a_bock_game(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(
        open_person, e2e_server, member_of, page_errors, form_factor, declaring=TwoPassedInBockTable
    )
    declaring = table.declaring
    assert isinstance(declaring, TwoPassedInBockTable)
    first, second = declaring.counts

    assert second == first - 1
    expect_the_count(table)


@pytest.mark.parametrize("form_factor", [pytest.param(PHONE, id="390")])
def test_a_table_without_bock_shows_nothing_of_it(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor)

    for person in table.everyone:
        expect(person.locator(".plaque")).to_be_visible()
        expect(person.locator(RULE_CHIP).filter(has_text=BOCK_WORD)).to_have_count(0)
        expect(person.locator(BOCK_LINE)).to_have_count(0)
    assert table.view(table.declarer_seat)["bock"] is None


def expect_the_kontra_row_to_hold_the_factor(table: PlayingTable) -> None:
    result = table.result()
    kontra_word = text(SOURCE_LANGUAGE, "result.wordKontra")
    kontra = text(SOURCE_LANGUAGE, "result.wordFactor", word=kontra_word, factor=str(result["kontra"]["factor"]))
    bock = text(SOURCE_LANGUAGE, "bock.factor", factor=str(result["bock_factor"]))
    doubled_by_loss = 1 if result["won"] else 2
    assert abs(result["score"]) == (
        result["settled_value"] * doubled_by_loss * result["kontra"]["factor"] * result["bock_factor"]
    )
    for person in table.everyone:
        row = person.locator(CARD).locator(".ladder").nth(1)
        expect(row.locator("> *")).to_have_text([kontra, bock])
        expect(person.locator(CARD).locator(".value")).to_have_text(signed(result["score"]))


@pytest.mark.parametrize("form_factor", [pytest.param(PHONE, id="390")])
def test_a_bock_game_with_kontra_holds_the_factor_beside_the_word(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, declaring=KontraBockTable)
    say_kontra_as_an_opponent(table)
    table.play_out(CARDS_IN_A_GAME)

    expect_the_kontra_row_to_hold_the_factor(table)
    assert page_errors == []


class BockRamschTable(RamschTable):
    """A Ramsch table whose first Ramsch starts a Bock round, so the second Ramsch is a Bock game."""

    options: ClassVar[dict[str, Any]] = {
        "ramsch": RAMSCH_OPTIONS,
        "bock": {"triggers": ["passed-in"], "overlap": "append"},
    }

    def deal_the_next_hand(self) -> None:
        for seat in self.names:
            self.sessions[seat].post(
                f"{self.api_path}{TABLE_READY_SUFFIX}",
                {"command_id": self._command_id(), "ordinal": self.view(seat)["result"]["ordinal"]},
            )
        for person in self.everyone:
            expect(person.locator(CARD)).to_have_count(0)
        self.seat_at = {chair["hand"]["position"]: chair["seat"] for chair in self.view(1)["chairs"]}


@pytest.mark.parametrize("form_factor", [pytest.param(PHONE, id="390")])
def test_a_bock_ramsch_holds_the_factor_after_its_other_chips(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = BockRamschTable(open_person, e2e_server, member_of, page_errors, form_factor)
    table.pass_all()
    table.play_out()
    table.deal_the_next_hand()
    table.pass_all()
    table.play_out()

    result = table.result()
    assert result["bock_factor"] > 1
    bock = text(SOURCE_LANGUAGE, "bock.factor", factor=str(result["bock_factor"]))
    scores = [each["score"] for each in result["seats"]]
    leader = max(scores) if result["durchmarsch_seat"] is not None else min(scores)
    for person in table.everyone:
        card = person.locator(CARD)
        expect(card.locator(".ladder > *").last).to_have_text(bock)
        expect(card.locator(".value")).to_have_text(signed(leader))
    assert page_errors == []
