import json
import re
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.engine.bidding import VALID_BIDS
from skat.engine.tricks import CARDS_IN_A_GAME
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.result_card import CARD, MINUS, TIMES, loosely

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

BIDDING = text(SOURCE_LANGUAGE, "table.bidding")
PASSED_IN = text(SOURCE_LANGUAGE, "table.passedIn")
RULE_CHIP = ".rulepill .chip"
BOCK_COUNT = f"{RULE_CHIP} .n"
BOCK_LINE = ".plaque .bock-line"


class BockTable(DeclaringTable):
    """A table whose Bock rounds start with a passed-in hand, opened through the API.

    The first hands are passed in, so the table has a Bock round before the first game: the middlehand of the hand dealt
    after them bids the lowest value and declares. `counts` holds the games to come after each passed-in hand.
    """

    hands_passed_in = 1

    def _open_table(self, opener: Page, server: RunningServer) -> str:
        options = {"bock": {"triggers": ["passed-in"], "overlap": "append"}}
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


class TwoPassedInBockTable(BockTable):
    hands_passed_in = 2


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
        expect(person.locator(BOCK_LINE)).to_have_text(text(SOURCE_LANGUAGE, "bock.factor", factor=str(factor)))


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
        expect(person.locator(RULE_CHIP)).to_have_count(0)
        expect(person.locator(BOCK_LINE)).to_have_count(0)
    assert table.view(table.declarer_seat)["bock"] is None
