import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.table.auction import AuctionAction
from skat.web.auction import TABLE_AUCTION_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.people import DESKTOP, PHONE
from tests.e2e.support.tables import open_new_table, sit_in, table_id_of, watch
from tests.e2e.support.words import catalog_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

SMALL_PHONE = {"viewport": {"width": 360, "height": 740}, "is_mobile": True, "has_touch": True}
WIDTHS = [pytest.param(SMALL_PHONE, id="360"), pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1280")]
BIDDING = catalog_text("bidding")
HOLD = catalog_text("hold")
PASS = catalog_text("pass")
LOWEST_BID = 18
SKAT_CARD = ".skat-card"
LADDER = ".ladder"
HELD = ".ladder .held"
LIT = ".ladder .now"
HIGHER = ".ladder .higher button"
MAIN = ".bid-buttons .button-stage"


@dataclass(frozen=True)
class Table:
    server: RunningServer
    id: str
    forehand: Page
    middlehand: Page
    rearhand: Page
    watcher: Page

    @property
    def everyone(self) -> tuple[Page, ...]:
        return (self.forehand, self.middlehand, self.rearhand, self.watcher)


def answer_of(person: Page, table: Table) -> dict[str, Any]:
    return person.request.get(f"{table.server.base_url}{TABLES_PATH}/{table.id}").json()


def position_of(person: Page, server: RunningServer, table_id: str) -> str:
    answer = person.request.get(f"{server.base_url}{TABLES_PATH}/{table_id}").json()
    return next(chair["hand"]["position"] for chair in answer["chairs"] if chair["is_mine"])


def dealt_table(
    open_person: Callable[..., Page],
    server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    *,
    console: bool = True,
) -> Table:
    def person(username: str) -> Page:
        return record_page_errors(open_person(username=username, **form_factor), page_errors, console=console)

    anna = person("anna")
    path = open_new_table(anna, server)
    ben, cleo, dora = person("ben"), person("cleo"), person("dora")
    for looker in (ben, cleo, dora):
        watch(looker, server, path)
    sit_in(ben, 2)
    expect(ben.locator(".chair[data-seat='2'] .plate")).to_contain_text("ben")
    sit_in(cleo, 3)
    for looker in (anna, ben, cleo, dora):
        expect(looker.locator(SKAT_CARD)).to_have_count(2)
    table_id = table_id_of(path)
    by_position = {position_of(player, server, table_id): player for player in (anna, ben, cleo)}
    return Table(server, table_id, by_position["forehand"], by_position["middlehand"], by_position["rearhand"], dora)


def step(person: Page, table: Table, action: AuctionAction, value: int | None = None) -> None:
    """A step taken behind the page, as the player's other device would."""
    payload: dict[str, Any] = {
        "command_id": uuid.uuid4().hex,
        "version": answer_of(person, table)["version"],
        "action": action.value,
    }
    if value is not None:
        payload["value"] = value
    response = person.request.post(
        f"{table.server.base_url}{TABLES_PATH}/{table.id}{TABLE_AUCTION_SUFFIX}", data=payload
    )
    assert response.ok, response.text()


def word_of(person: Page, table: Table, viewer: Page) -> dict[str, Any] | None:
    """`person`'s last word in the auction, read through `viewer`'s answer."""
    answer = answer_of(viewer, table)
    seat = next(chair["seat"] for chair in answer_of(person, table)["chairs"] if chair["is_mine"])
    return next((word for word in answer["hand"]["auction"]["words"] if word["seat"] == seat), None)


def assert_no_controls(person: Page) -> None:
    expect(person.locator(LADDER)).to_have_count(0)
    expect(person.get_by_role("button", name=PASS)).to_have_count(0)


def assert_page_fits(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_middlehand_opens_the_auction_and_the_forehand_answers(
    open_person: Callable[..., Page], e2e_server: RunningServer, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = dealt_table(open_person, e2e_server, page_errors, form_factor)
    middlehand = table.middlehand

    expect(middlehand.locator(HELD)).to_have_count(0)
    expect(middlehand.locator(LIT)).to_have_text(str(LOWEST_BID))
    expect(middlehand.locator(MAIN)).to_have_text(str(LOWEST_BID))
    expect(middlehand.get_by_role("button", name=PASS)).to_be_visible()
    assert middlehand.locator(HIGHER).first.inner_text() == "20"
    assert middlehand.locator(HIGHER).last.inner_text() == "264"
    assert_page_fits(middlehand)

    middlehand.locator(MAIN).click()

    expect(table.forehand.get_by_role("button", name=HOLD)).to_be_visible()
    assert_no_controls(middlehand)
    assert word_of(middlehand, table, table.watcher) == {
        "seat": word_of(middlehand, table, table.watcher)["seat"],
        "action": AuctionAction.BID.value,
        "value": LOWEST_BID,
    }
