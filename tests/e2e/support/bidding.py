"""Three people at a dealt table in its auction with a watcher beside them, and the bid bar as a test reaches it."""

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from playwright.sync_api import Locator, Page, expect

from skat.engine.bidding import VALID_BIDS
from skat.table.auction import AuctionAction
from skat.table.records import PlanMode, TableStyle
from skat.web.auction import (
    TABLE_AUCTION_BID_SUFFIX,
    TABLE_AUCTION_HOLD_SUFFIX,
    TABLE_AUCTION_PASS_SUFFIX,
    TABLE_AUCTION_PLAN_SUFFIX,
    TABLE_AUCTION_PLAY_SUFFIX,
)
from skat.web.tables import TABLES_PATH, PlanKind
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.style import give_the_table_its_style
from tests.e2e.support.tables import open_new_table, sit_in, table_id_of, watch

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer

PASS = text(SOURCE_LANGUAGE, "bid.pass")
UP_TO = text(SOURCE_LANGUAGE, "bid.upTo")
YOU = text(SOURCE_LANGUAGE, "table.sideYou")
# A request on a connection the server closed for idling meets a reset; Playwright retries only that error.
RESET_RETRIES = 3
SKAT_CARD = ".skat-card"
BAR = ".bid"
STEP_KEY = ".bid-keys .button-stage"
LIMIT_KEY = ".bid-keys .button-brass"
PASS_KEY = ".bid-chips .button-glass"
CHIPS = ".bid-chip:not(.more)"
MORE = ".bid-chip.more"
SCALE = ".scale"
LIMIT_VALUE = ".bid-line .bis b"


@dataclass(frozen=True)
class BiddingTable:
    server: RunningServer
    id: str
    forehand: Page
    middlehand: Page
    rearhand: Page
    watcher: Page

    @property
    def everyone(self) -> tuple[Page, ...]:
        return (self.forehand, self.middlehand, self.rearhand, self.watcher)


def answer_of(person: Page, table: BiddingTable) -> dict[str, Any]:
    return person.request.get(f"{table.server.base_url}{TABLES_PATH}/{table.id}", max_retries=RESET_RETRIES).json()


def position_of(person: Page, server: RunningServer, table_id: str) -> str:
    answer = person.request.get(f"{server.base_url}{TABLES_PATH}/{table_id}", max_retries=RESET_RETRIES).json()
    return next(chair["hand"]["position"] for chair in answer["chairs"] if chair["is_mine"])


def dealt_table(
    open_person: Callable[..., Page],
    server: RunningServer,
    page_errors: list[str],
    form_factor: dict[str, Any],
    *,
    console: bool = True,
    style: TableStyle = TableStyle.KLASSIK,
) -> BiddingTable:
    def person(username: str) -> Page:
        return record_page_errors(open_person(username=username, **form_factor), page_errors, console=console)

    anna = person("anna")
    path = open_new_table(anna, server)
    ben, cleo, dora = person("ben"), person("cleo"), person("dora")
    for looker in (ben, cleo, dora):
        watch(looker, server, path)
    sit_in(ben, 2)
    expect(ben.locator(".chair[data-seat='2'] .plate")).to_contain_text(YOU)
    sit_in(cleo, 3)
    for looker in (anna, ben, cleo, dora):
        expect(looker.locator(SKAT_CARD)).to_have_count(2)
    table_id = table_id_of(path)
    by_position = {position_of(player, server, table_id): player for player in (anna, ben, cleo)}
    give_the_table_its_style(anna, (anna, ben, cleo, dora), style)
    return BiddingTable(
        server, table_id, by_position["forehand"], by_position["middlehand"], by_position["rearhand"], dora
    )


STEP_SUFFIXES = {
    AuctionAction.BID: TABLE_AUCTION_BID_SUFFIX,
    AuctionAction.HOLD: TABLE_AUCTION_HOLD_SUFFIX,
    AuctionAction.PASS: TABLE_AUCTION_PASS_SUFFIX,
    AuctionAction.PLAY: TABLE_AUCTION_PLAY_SUFFIX,
}


def send(person: Page, table: BiddingTable, suffix: str, payload: dict[str, Any]) -> None:
    response = person.request.post(
        f"{table.server.base_url}{TABLES_PATH}/{table.id}{suffix}",
        data={"command_id": uuid.uuid4().hex, **payload},
        headers={"Origin": table.server.base_url},
        max_retries=RESET_RETRIES,
    )
    assert response.ok, response.text()


def step(person: Page, table: BiddingTable, action: AuctionAction, value: int | None = None) -> None:
    """A step taken behind the page, as the player's other device would."""
    payload: dict[str, Any] = {"version": answer_of(person, table)["version"]}
    if value is not None:
        payload["value"] = value
    send(person, table, STEP_SUFFIXES[action], payload)


def limit_at(value: int, mode: PlanMode) -> dict[str, Any]:
    """A limit as the plan command and the owner's answer name it."""
    return {"kind": PlanKind.LIMIT.value, "value": value, "mode": mode.value}


def plan_ahead(person: Page, table: BiddingTable, plan: dict[str, Any]) -> None:
    """A plan set behind the page, as the player's other device would."""
    send(person, table, TABLE_AUCTION_PLAN_SUFFIX, {"plan": plan})


def auction_of(person: Page, table: BiddingTable) -> dict[str, Any]:
    """The auction as `person`'s own answer tells it."""
    return answer_of(person, table)["hand"]["auction"]


def own_word(person: Page, table: BiddingTable) -> tuple[str, int | None]:
    """`person`'s last word in the auction, from their own answer."""
    answer = answer_of(person, table)
    seat = next(chair["seat"] for chair in answer["chairs"] if chair["is_mine"])
    word = next(word for word in answer["hand"]["auction"]["words"] if word["seat"] == seat)
    return word["action"], word["value"]


def own_plan(person: Page, table: BiddingTable) -> dict[str, Any] | None:
    """`person`'s plan for the auction, from their own answer."""
    return auction_of(person, table)["plan"]


def own_values(person: Page, table: BiddingTable) -> list[int]:
    """The values `person`'s cards reach, lowest first, from their own answer: the deal is the server's."""
    return [reached["value"] for reached in auction_of(person, table)["hand_values"]]


def first_bid_above(value: int) -> int:
    return next(bid for bid in VALID_BIDS if bid > value)


def chip(person: Page, value: int) -> Locator:
    return person.locator(".bid-chips").get_by_role("button", name=f"{UP_TO} {value}", exact=True)


def on_the_scale(person: Page, value: int) -> Locator:
    return person.locator(SCALE).get_by_role("button", name=str(value), exact=True)


def pass_key(person: Page) -> Locator:
    return person.get_by_role("button", name=PASS, exact=True)


def assert_no_controls(person: Page) -> None:
    expect(person.locator(BAR)).to_have_count(0)
    expect(pass_key(person)).to_have_count(0)


def assert_page_fits(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
