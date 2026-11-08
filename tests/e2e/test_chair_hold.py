from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import DESKTOP, PHONE
from tests.e2e.support.server import skat_on_new_database
from tests.e2e.support.tables import (
    SIT_DOWN,
    assert_never_reloaded,
    mark_page,
    open_new_table,
    plate_of,
    sit_in,
    watch,
)
from tests.e2e.support.words import catalog_text

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

SMALL_PHONE = {"viewport": {"width": 360, "height": 740}, "is_mobile": True, "has_touch": True}
WIDTHS = [pytest.param(SMALL_PHONE, id="360"), pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1280")]
SEAT_AWAY = catalog_text("seatAway")
CHAIR_HOLD_SECONDS = 5
FREED_WITHIN_MILLISECONDS = (CHAIR_HOLD_SECONDS + 10) * 1000


@pytest.fixture(scope="session")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """This module's Skat, with a chair hold short enough for a browser to wait out."""
    with skat_on_new_database(tmp_path_factory, chair_hold_seconds=CHAIR_HOLD_SECONDS) as server:
        yield server


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_away_members_chair_turns_free_on_every_open_page_after_the_hold_and_the_next_member_takes_it(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    opener = record_page_errors(open_person(username="anna", **form_factor), page_errors)
    path = open_new_table(opener, e2e_server)
    onlooker = record_page_errors(open_person(username="ben", **form_factor), page_errors)
    watch(onlooker, e2e_server, path)
    mark_page(onlooker)
    opener.close()
    expect(plate_of(onlooker, 1)).to_contain_text(SEAT_AWAY)

    expect(onlooker.locator(".chair[data-seat='1']").get_by_role("button", name=SIT_DOWN)).to_be_visible(
        timeout=FREED_WITHIN_MILLISECONDS
    )
    expect(plate_of(onlooker, 1)).not_to_contain_text("anna")
    sit_in(onlooker, 1)

    expect(plate_of(onlooker, 1)).to_have_text("ben")
    assert_never_reloaded(onlooker)
