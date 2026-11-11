from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.engine.tricks import CARDS_IN_A_GAME
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import FORM_FACTORS
from tests.e2e.support.server import skat_on_new_database
from tests.e2e.support.tables import SIT_DOWN, open_new_table, watch

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

SEAT_AWAY = text(SOURCE_LANGUAGE, "table.seatAway")
CHAIR_HOLD_SECONDS = 5
FREED_WITHIN_MILLISECONDS = (CHAIR_HOLD_SECONDS + 10) * 1000


@pytest.fixture(scope="session")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """This module's Skat, with a chair hold short enough for a browser to wait out."""
    with skat_on_new_database(tmp_path_factory, chair_hold_seconds=CHAIR_HOLD_SECONDS) as server:
        yield server


@pytest.fixture
def a_table_between_games(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[[dict[str, Any]], PlayingTable]:
    def deal(form_factor: dict[str, Any]) -> PlayingTable:
        table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, game="kreuz")
        table.play_out(CARDS_IN_A_GAME)
        return table

    return deal


@pytest.mark.parametrize("form_factor", FORM_FACTORS)
def test_a_member_who_closed_every_tab_between_games_keeps_the_chair_after_the_hold_and_finds_the_table_as_left(
    a_table_between_games: Callable[[dict[str, Any]], PlayingTable],
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = a_table_between_games(form_factor)
    away_seat = next(seat for seat in table.names if seat != table.declarer_seat)
    other = table.pages[table.declarer_seat]
    away_chair = other.locator(f".chair[data-seat='{away_seat}']")
    table.pages[away_seat].close()
    expect(away_chair).to_contain_text(SEAT_AWAY)
    # A table with no hand dealt frees a chair after the same hold, which started later than the dealt table's.
    control_owner = open_person(username="dora", **form_factor)
    control_path = open_new_table(control_owner, e2e_server)
    onlooker = open_person(username="erik", **form_factor)
    watch(onlooker, e2e_server, control_path)
    control_owner.close()
    expect(onlooker.locator(".chair[data-seat='1']").get_by_role("button", name=SIT_DOWN)).to_be_visible(
        timeout=FREED_WITHIN_MILLISECONDS
    )

    expect(away_chair).to_contain_text(SEAT_AWAY)
    back = table.pages[away_seat].context.new_page()
    back.goto(other.url)

    expect(away_chair).not_to_contain_text(SEAT_AWAY)
    assert page_errors == []
