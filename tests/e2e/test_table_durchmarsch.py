from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.people import PHONE
from tests.e2e.support.ramsch import RamschTable
from tests.e2e.support.result_card import CARD, WON
from tests.e2e.support.server import AlwaysTheSameDeal, skat_on_new_database

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

DEAL_WHERE_ANNA_SWEEPS = 903
SWEEPER_SEAT = 1
DURCHMARSCH = text(SOURCE_LANGUAGE, "result.durchmarsch")


@pytest.fixture(scope="module")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """This module's Skat, whose Ramsch played out card by smallest card gives Anna every trick."""
    with skat_on_new_database(tmp_path_factory, random_source=AlwaysTheSameDeal(DEAL_WHERE_ANNA_SWEEPS)) as server:
        yield server


def test_the_player_who_takes_every_trick_reads_won_with_a_tick_and_the_others_read_durchmarsch(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, PHONE)
    table.pass_all()
    table.play_out()

    assert table.result()["durchmarsch_seat"] == SWEEPER_SEAT
    sweeper = table.pages[SWEEPER_SEAT].locator(CARD)
    expect(sweeper.locator("h3")).to_have_text(WON)
    expect(sweeper.locator("h3 svg")).to_have_count(1)
    for person in (table.pages[2], table.pages[3], table.watcher):
        card = person.locator(CARD)
        expect(card.locator("h3")).to_have_text(DURCHMARSCH)
        expect(card.locator("h3 svg")).to_have_count(0)
    assert page_errors == []
