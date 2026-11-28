from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.engine.tricks import CARDS_IN_A_GAME
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.result_card import CARD, MINUS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e


def shown(gain: int) -> str:
    return f"+{gain}" if gain > 0 else str(gain).replace("-", MINUS)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_with_motion_allowed_every_viewer_reads_each_seats_final_gain(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(
        open_person, e2e_server, member_of, page_errors, {**form_factor, "reduced_motion": "no-preference"}
    )
    table.play_out(CARDS_IN_A_GAME)

    for person in table.everyone:
        for gain in table.result()["gains"]:
            cell = person.locator(f"{CARD} .reck[data-seat='{gain['seat']}'] .dl")
            expect(cell).to_have_text(shown(gain["gain"]))
    assert page_errors == []
