import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from playwright.sync_api import Page, expect

from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.mcp import AUCTION_PASS_TOOL, SIT_DOWN_TOOL
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.pushing import TABLE_PUSHING_PUSH_SUFFIX, TABLE_PUSHING_PUT_BACK_SUFFIX, TABLE_PUSHING_TAKE_SUFFIX
from skat.web.tables import TABLE_PAGE_PREFIX, TABLE_STAND_SUFFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import AddressedSession
from tests.e2e.support.tables import sit_in, watch
from tests.support.signed_in import seed_member

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.people import McpAgent
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

PLAQUE = ".plaque.ramsch"
TURN_CHAIR = ".chair.turn"
BUBBLE = ".chair .bubble.word"
BIDDING = text(SOURCE_LANGUAGE, "table.bidding")
AGENT_SEAT = 3
TWO_LINES = 2


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
        console: bool = True,
    ) -> None:
        self.agent = agent
        seated = ("anna", "ben") if agent else ("anna", "ben", "cleo")
        people = {
            username: record_page_errors(open_person(username=username, **form_factor), page_errors, console=console)
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
            for bubble in person.locator(BUBBLE).all():
                box = bubble.bounding_box()
                assert box is not None
                assert box["x"] >= 0
                assert box["x"] + box["width"] <= viewport["width"]

    def expect_the_plaque_lines_to_read_alike(self, people: list[Page]) -> None:
        for person in people:
            sizes = person.locator(f"{PLAQUE} .game:not(.pushes)").evaluate_all(
                "lines => lines.map(line => getComputedStyle(line).fontSize)"
            )
            assert len(sizes) >= TWO_LINES
            assert len(set(sizes)) == 1


def deal(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
    rule: str = "jacks-stay",
    *,
    console: bool = True,
) -> RamschStageTable:
    return RamschStageTable(open_person, e2e_server, member_of, page_errors, form_factor, rule=rule, console=console)
