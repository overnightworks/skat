import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect

from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.mcp import AUCTION_PASS_TOOL, SIT_DOWN_TOOL
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.pushing import TABLE_PUSHING_PUSH_SUFFIX, TABLE_PUSHING_PUT_BACK_SUFFIX, TABLE_PUSHING_TAKE_SUFFIX
from skat.web.tables import TABLE_PAGE_PREFIX, TABLE_STAND_SUFFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import AddressedSession
from tests.e2e.support.people import DESKTOP, PHONE, WIDTHS, McpAgent
from tests.e2e.support.tables import sit_in, watch
from tests.support.signed_in import seed_member

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

PLAQUE = ".plaque.ramsch"
TURN_CHAIR = ".chair.turn"
BUBBLE = ".chair .bubble.word"
SKAT_CARDS = ".skat-spot .skat-card"
LAID_CARDS = ".trick .laid"
DECLARER_MARK = ".mark.declarer"
RAMSCH = text(SOURCE_LANGUAGE, "table.ramsch")
PUSH_WORD = text(SOURCE_LANGUAGE, "table.push")
BIDDING = text(SOURCE_LANGUAGE, "table.bidding")
WAITING_FOR_PLAYERS = text(SOURCE_LANGUAGE, "table.waitingForPlayers")
CHOOSES = text(SOURCE_LANGUAGE, "table.chooses")
DISCARDS = text(SOURCE_LANGUAGE, "table.discards")
THINKS = text(SOURCE_LANGUAGE, "table.thinks")
CARDS_AFTER_A_TAKE = 12
POSITIONS = ("forehand", "middlehand", "rearhand")
AGENT_SEAT = 3


def pushes(count: int) -> str:
    return text(SOURCE_LANGUAGE, "table.pushCount", count=count)


def factor(value: int) -> str:
    return text(SOURCE_LANGUAGE, "table.pushFactor", factor=str(value))


def ramsch_options(rule: str) -> dict[str, Any]:
    return {
        "ramsch": {
            "occasion": "passed-in",
            "scoring": "points",
            "jungfrau": "doubles-loser",
            "durchmarsch": "wins-120",
            "pushing": {"rule": rule},
        }
    }


class RamschStageTable:
    """A table with Ramsch and pushing opened through the API, three browsers at its chairs and one watching; the
    stage is stepped through the API and every page is read as a person reads it. With an agent, it sits at the third
    chair instead of the third person and passes through its tool.
    """

    def __init__(
        self,
        open_person: Callable[..., Page],
        server: RunningServer,
        member_of: Callable[[Page], SeededMember],
        page_errors: list[str],
        form_factor: dict[str, Any],
        *,
        rule: str,
        agent: McpAgent | None = None,
    ) -> None:
        self.agent = agent
        seated = ("anna", "ben") if agent else ("anna", "ben", "cleo")
        people = {
            username: record_page_errors(open_person(username=username, **form_factor), page_errors)
            for username in (*seated, "dora")
        }
        self.sessions = {
            seat: AddressedSession(server, member_of(people[username])) for seat, username in enumerate(seated, start=1)
        }
        if agent:
            agent.request("tools/list")
            account = server.stores.accounts.get(agent.subject)
            assert account is not None
            self.sessions[AGENT_SEAT] = AddressedSession(
                server, seed_member(server.stores, server.config, account=account)
            )
        created = self.sessions[1].post(
            TABLES_PATH, {"command_id": self._command(), "series_length": 36, "options": ramsch_options(rule)}
        )
        self.api_path = f"{TABLES_PATH}/{json.loads(created)['id']}"
        page_path = f"{TABLE_PAGE_PREFIX}{self.api_path.removeprefix(TABLES_PATH + '/')}"
        for person in people.values():
            watch(person, server, page_path)
        for seat, username in enumerate(seated[1:], start=2):
            sit_in(people[username], seat)
        if agent:
            self._seat_agent(agent)
        self.pages = {seat: people[username] for seat, username in enumerate(seated, start=1)}
        self.watcher = people["dora"]
        self.everyone = [*self.pages.values(), self.watcher]
        expect(self.watcher.locator(".plaque")).to_contain_text(BIDDING)
        chairs = self.view(1)["chairs"]
        self.seat_at = {chair["hand"]["position"]: chair["seat"] for chair in chairs}
        self.names = {chair["seat"]: chair["occupant_name"] for chair in chairs}
        for position in ("middlehand", "rearhand", "forehand"):
            self.step(self.seat_at[position], TABLE_AUCTION_PASS_SUFFIX)
        expect(self.watcher.locator(PLAQUE)).to_be_visible()

    def _seat_agent(self, agent: McpAgent) -> None:
        failed, reason = agent.call(
            SIT_DOWN_TOOL, table_id=self.api_path.rsplit("/", 1)[1], seat=AGENT_SEAT, command_id=self._command()
        )
        assert not failed, reason

    @staticmethod
    def _command() -> str:
        return f"ramsch-stage-{uuid4().hex}"

    def view(self, seat: int) -> dict[str, Any]:
        return json.loads(self.sessions[seat].get(self.api_path))

    def step(self, seat: int, suffix: str, **fields: object) -> None:
        version = self.view(seat)["version"]
        if self.agent and seat == AGENT_SEAT:
            assert suffix == TABLE_AUCTION_PASS_SUFFIX
            failed, text = self.agent.call(
                AUCTION_PASS_TOOL, table_id=self.api_path.rsplit("/", 1)[1], command_id=self._command(), version=version
            )
            assert not failed, text
            return
        self.sessions[seat].post(
            f"{self.api_path}{suffix}", {"command_id": self._command(), "version": version, **fields}
        )

    def seat_of(self, position: str) -> int:
        return self.seat_at[position]

    def name_of(self, position: str) -> str:
        return self.names[self.seat_of(position)]

    def push(self, position: str) -> None:
        self.step(self.seat_of(position), TABLE_PUSHING_PUSH_SUFFIX)

    def take(self, position: str) -> None:
        self.step(self.seat_of(position), TABLE_PUSHING_TAKE_SUFFIX)

    def put_back_two_cards_that_are_no_jack(self, position: str) -> None:
        seat = self.seat_of(position)
        held = self.view(seat)["hand"]["own_cards"]
        self.step(seat, TABLE_PUSHING_PUT_BACK_SUFFIX, cards=[card for card in held if card["rank"] != "jack"][:2])

    def lead_a_card(self, position: str) -> None:
        seat = self.seat_of(position)
        card = self.view(seat)["hand"]["playing"]["legal_cards"][0]
        self.step(seat, TABLE_CARD_SUFFIX, suit=card["suit"], rank=card["rank"])

    def stand_up(self, position: str) -> None:
        self.sessions[self.seat_of(position)].post(
            f"{self.api_path}{TABLE_STAND_SUFFIX}", {"command_id": self._command()}
        )

    def reload_everyone(self) -> None:
        for person in self.everyone:
            person.reload()
            expect(person.locator(".chair")).to_have_count(3)

    def chair(self, person: Page, position: str):
        return person.locator(f".chair[data-seat='{self.seat_of(position)}']")

    def expect_the_turn_at(self, position: str) -> None:
        for person in self.everyone:
            expect(person.locator(TURN_CHAIR)).to_have_count(1)
            expect(person.locator(TURN_CHAIR)).to_have_attribute("data-seat", str(self.seat_of(position)))

    def expect_nothing_to_overflow(self, people: list[Page] | None = None) -> None:
        for person in self.everyone if people is None else people:
            assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            plaque = person.locator(PLAQUE).bounding_box()
            viewport = person.viewport_size
            assert plaque is not None
            assert viewport is not None
            assert plaque["x"] >= 0
            assert plaque["x"] + plaque["width"] <= viewport["width"]


def deal(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
    rule: str = "jacks-stay",
) -> RamschStageTable:
    return RamschStageTable(open_person, e2e_server, member_of, page_errors, form_factor, rule=rule)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_everyone_sees_who_acts_and_the_pushes_with_their_factor_and_a_reload_changes_nothing(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, form_factor)
    forehand = table.name_of("forehand")
    on_turn = table.pages[table.seat_of("forehand")]

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(RAMSCH)
        expect(person.locator(PLAQUE)).not_to_contain_text(BIDDING)
        expect(person.locator(SKAT_CARDS)).to_have_count(2)
        expect(person.locator(DECLARER_MARK)).to_have_count(0)
        if person is not on_turn:
            expect(person.locator(PLAQUE)).to_contain_text(f"{forehand} {CHOOSES}")
    expect(on_turn.locator(PLAQUE)).not_to_contain_text(CHOOSES)
    table.expect_the_turn_at("forehand")
    table.expect_nothing_to_overflow()

    table.take("forehand")

    for person in table.everyone:
        if person is not on_turn:
            expect(person.locator(PLAQUE)).to_contain_text(f"{forehand} {DISCARDS}")
            expect(table.chair(person, "forehand").locator(".count-tag")).to_contain_text(str(CARDS_AFTER_A_TAKE))
        expect(person.locator(SKAT_CARDS)).to_have_count(0)

    table.put_back_two_cards_that_are_no_jack("forehand")
    table.push("middlehand")

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(pushes(1))
        expect(person.locator(PLAQUE).locator(".pushes b")).to_have_text(factor(2))
        expect(table.chair(person, "middlehand").locator(".bubble.word")).to_contain_text(PUSH_WORD)
        expect(person.locator(BUBBLE)).to_have_count(1)
        expect(person.locator(SKAT_CARDS)).to_have_count(2)
    table.expect_the_turn_at("rearhand")
    for person in table.everyone:
        if person is not table.pages[table.seat_of("rearhand")]:
            expect(person.locator(PLAQUE)).to_contain_text(f"{table.name_of('rearhand')} {CHOOSES}")
    table.expect_nothing_to_overflow()

    table.reload_everyone()

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(pushes(1))
        expect(person.locator(PLAQUE).locator(".pushes b")).to_have_text(factor(2))
        expect(table.chair(person, "middlehand").locator(".bubble.word")).to_contain_text(PUSH_WORD)
    table.expect_the_turn_at("rearhand")


def test_a_table_that_does_not_double_counts_the_pushes_without_a_factor(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, PHONE, rule="no-doubling")

    table.push("forehand")
    table.push("middlehand")

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(pushes(2))
        expect(person.locator(PLAQUE).locator(".pushes b")).to_have_count(0)
        expect(person.locator(BUBBLE)).to_have_count(2)


@pytest.mark.parametrize("form_factor", [WIDTHS[0], WIDTHS[2]])
def test_the_play_keeps_the_count_and_draws_the_trick_without_a_declarer(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, form_factor)
    table.push("forehand")
    table.push("middlehand")
    table.take("rearhand")
    table.put_back_two_cards_that_are_no_jack("rearhand")

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(pushes(2))
        expect(person.locator(PLAQUE).locator(".pushes b")).to_have_text(factor(4))
        expect(person.locator(PLAQUE)).not_to_contain_text(BIDDING)
        expect(person.locator(BUBBLE)).to_have_count(0)
        expect(person.locator(SKAT_CARDS)).to_have_count(0)
    table.expect_the_turn_at("forehand")

    table.lead_a_card("forehand")

    for person in table.everyone:
        expect(person.locator(LAID_CARDS)).to_have_count(1)
        expect(person.locator(DECLARER_MARK)).to_have_count(0)
        expect(person.locator(PLAQUE)).to_contain_text(pushes(2))
    table.expect_the_turn_at("middlehand")
    table.expect_nothing_to_overflow()

    table.reload_everyone()

    for person in table.everyone:
        expect(person.locator(PLAQUE).locator(".pushes b")).to_have_text(factor(4))
        expect(person.locator(LAID_CARDS)).to_have_count(1)
    table.expect_the_turn_at("middlehand")


def test_an_open_chair_makes_the_plaque_wait_and_leaves_nobody_on_turn(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, PHONE)
    left = table.seat_of("rearhand")
    still_seated = [person for seat, person in table.pages.items() if seat != left]

    table.stand_up("rearhand")

    for person in (*still_seated, table.watcher):
        expect(person.locator(PLAQUE)).to_contain_text(WAITING_FOR_PLAYERS)
        expect(person.locator(PLAQUE)).not_to_contain_text(CHOOSES)
        expect(person.locator(TURN_CHAIR)).to_have_count(0)
    table.expect_nothing_to_overflow([*still_seated, table.watcher])


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_agent_on_turn_wears_denkt_over_the_turn_mark_for_everyone(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschStageTable(
        open_person,
        e2e_server,
        member_of,
        page_errors,
        form_factor,
        rule="jacks-stay",
        agent=McpAgent(e2e_server, "agent-subject-ramsch-thinker"),
    )
    agent_position = next(position for position in POSITIONS if table.seat_of(position) == AGENT_SEAT)
    for position in POSITIONS[: POSITIONS.index(agent_position)]:
        table.push(position)

    table.expect_the_turn_at(agent_position)
    for person in table.everyone:
        chair = table.chair(person, agent_position)
        thinks = chair.locator(".mark.think")
        expect(person.locator(".mark.think")).to_have_count(1)
        expect(thinks).to_be_visible()
        think_box = thinks.bounding_box()
        turn_box = chair.locator(".mark.turn").bounding_box()
        chair_box = chair.bounding_box()
        assert think_box is not None
        assert turn_box is not None
        assert chair_box is not None
        assert chair_box["x"] <= think_box["x"]
        assert think_box["x"] + think_box["width"] <= chair_box["x"] + chair_box["width"]
        assert think_box["x"] <= turn_box["x"]
        assert think_box["y"] <= turn_box["y"]
        assert turn_box["x"] + turn_box["width"] <= think_box["x"] + think_box["width"]
        assert turn_box["y"] + turn_box["height"] <= think_box["y"] + think_box["height"]
        assert thinks.evaluate(
            "think => { const box = think.closest('.chair').querySelector('.mark.turn').getBoundingClientRect(); "
            "const top = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2); "
            "return top?.closest('.mark') === think }"
        )
        if form_factor is DESKTOP:
            expect(thinks).to_contain_text(THINKS)
            assert thinks.evaluate("mark => getComputedStyle(mark).fontSize") != "0px"
    table.expect_nothing_to_overflow()

    table.reload_everyone()

    for person in table.everyone:
        expect(table.chair(person, agent_position).locator(".mark.think")).to_be_visible()
