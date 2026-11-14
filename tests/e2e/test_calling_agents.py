"""A member of the calling group opens the pill „Agenten“, taps „Rufen“ on an agent's row and the agent sits, or taps
„Bitten zu gehen“ on the row of a seated agent and the chair opens.
"""

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from skat.web.calling import AGENT_ADDERS_GROUP
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.kit_words import kit_text
from tests.e2e.support.listening_agent import ListeningAgent
from tests.e2e.support.people import DESKTOP, WIDTHS
from tests.e2e.support.server import skat_on_new_database
from tests.e2e.support.tables import open_new_table, plate_of, sit_in, watch

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from playwright.sync_api import Page

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

PILL = text(SOURCE_LANGUAGE, "agents.pill")
CALLING = kit_text("agent.calling")
BUSY = kit_text("agent.busy")
EMPTY = kit_text("agent.empty")
SEAT_FREE = text(SOURCE_LANGUAGE, "table.seatFree")
AI_MARK = "AI"
INVITATION_WITHIN_SECONDS = 15
# The list keeps this far from either edge of the viewport, in pixels.
EDGE_MARGIN = 16
# The page's fetches leave this long after the call, so they leave while the test already waits for the agent.
DELAY_FETCHES = """
    const send = window.fetch;
    window.fetch = (...request) => new Promise((resolve) => setTimeout(resolve, 300)).then(() => send(...request));
"""


def pill(person: Page):
    return person.get_by_role("button", name=PILL)


def wait_until_inside_the_margin(person: Page, selector: str) -> None:
    # The list follows its pill by animation frame, so the page is polled instead of read once.
    person.wait_for_function(
        """([selector, margin]) => {
            const { left, right } = document.querySelector(selector).getBoundingClientRect();
            return left >= margin - 0.5 && right <= innerWidth - margin + 0.5;
        }""",
        arg=[selector, EDGE_MARGIN],
    )


def call_label(name: str) -> str:
    return kit_text("agent.callLabel", name=name)


def ask_to_leave_label(name: str) -> str:
    return kit_text("agent.askToLeaveLabel", name=name)


def sits_note(name: str) -> str:
    return text(SOURCE_LANGUAGE, "table.agentSits", name=name)


@pytest.fixture
def caller(open_person: Callable[..., Page], realm_reusing_refresh_tokens: None, page_errors: list[str]) -> Page:
    return record_page_errors(open_person(username="felix", groups=(AGENT_ADDERS_GROUP,), **DESKTOP), page_errors)


@pytest.mark.usefixtures("realm_reusing_refresh_tokens")
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_member_calls_a_listening_agent_and_every_page_sees_it_sit(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict,
) -> None:
    felix = record_page_errors(
        open_person(username="felix-calls", groups=(AGENT_ADDERS_GROUP,), **form_factor), page_errors
    )
    path = open_new_table(felix, e2e_server)
    anna = record_page_errors(open_person(username="anna-watches", **DESKTOP), page_errors)
    watch(anna, e2e_server, path)
    agent = ListeningAgent(e2e_server, member_of(felix).account.id, "Leonardo", "agent-subject-leonardo")
    try:
        expect(pill(felix)).to_be_visible()
        pill(felix).click()
        felix.get_by_role("button", name=call_label("Leonardo")).click()
        expect(felix.get_by_text(CALLING)).to_be_visible()
        agent.accept(agent.invitation_within(felix, INVITATION_WITHIN_SECONDS))
        for person in (felix, anna):
            expect(plate_of(person, 2)).to_contain_text("Leonardo")
            expect(plate_of(person, 2)).to_contain_text(AI_MARK)
        expect(felix.get_by_text(sits_note("Leonardo"))).to_be_visible()
        expect(pill(anna)).to_have_count(0)
    finally:
        agent.close()


@pytest.mark.usefixtures("realm_reusing_refresh_tokens")
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_list_left_open_stays_inside_the_margin_when_the_hand_deals(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict,
) -> None:
    felix = record_page_errors(
        open_person(username="felix-open-list", groups=(AGENT_ADDERS_GROUP,), **form_factor), page_errors
    )
    path = open_new_table(felix, e2e_server)
    ben = record_page_errors(open_person(username="ben-sits", **DESKTOP), page_errors)
    watch(ben, e2e_server, path)
    sit_in(ben, 2)
    agent = ListeningAgent(e2e_server, member_of(felix).account.id, "Leonardo", "agent-subject-leonardo-deal")
    try:
        pill(felix).click()
        felix.get_by_role("button", name=call_label("Leonardo")).click()
        agent.accept(agent.invitation_within(felix, INVITATION_WITHIN_SECONDS))
        expect(plate_of(felix, 3)).to_contain_text("Leonardo")
        expect(felix.locator(".chair .mark.pos")).to_have_count(3)
        popover = felix.locator(".agents-pop")
        expect(popover).to_be_visible()

        wait_until_inside_the_margin(felix, ".agents-pop")
    finally:
        agent.close()


@pytest.mark.usefixtures("realm_reusing_refresh_tokens")
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_member_sends_a_seated_agent_away_mid_hand_and_the_row_offers_the_call_again(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict,
) -> None:
    felix = record_page_errors(
        open_person(username="felix-sends-away", groups=(AGENT_ADDERS_GROUP,), **form_factor), page_errors
    )
    path = open_new_table(felix, e2e_server)
    ben = record_page_errors(open_person(username="ben-keeps-his-chair", **DESKTOP), page_errors)
    watch(ben, e2e_server, path)
    sit_in(ben, 2)
    agent = ListeningAgent(e2e_server, member_of(felix).account.id, "Nova", "agent-subject-nova-leaves")
    try:
        pill(felix).click()
        felix.get_by_role("button", name=call_label("Nova")).click()
        agent.accept(agent.invitation_within(felix, INVITATION_WITHIN_SECONDS))
        expect(plate_of(felix, 3)).to_contain_text("Nova")
        expect(felix.locator(".chair .mark.pos")).to_have_count(3)

        felix.get_by_role("button", name=ask_to_leave_label("Nova")).click()

        for person in (felix, ben):
            expect(plate_of(person, 3)).to_contain_text(SEAT_FREE)
            expect(plate_of(person, 3)).not_to_contain_text("Nova")
        expect(felix.get_by_role("button", name=call_label("Nova"))).to_be_visible()
    finally:
        agent.close()


@pytest.mark.usefixtures("realm_reusing_refresh_tokens")
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_owner_outside_the_calling_group_sends_his_own_agent_away_from_the_page(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict,
) -> None:
    felix = record_page_errors(
        open_person(username="felix-calls-for-olga", groups=(AGENT_ADDERS_GROUP,), **DESKTOP), page_errors
    )
    path = open_new_table(felix, e2e_server)
    olga = record_page_errors(open_person(username="olga-owns-nova", **form_factor), page_errors)
    watch(olga, e2e_server, path)
    agent = ListeningAgent(e2e_server, member_of(olga).account.id, "Nova", "agent-subject-nova-of-olga")
    try:
        pill(felix).click()
        felix.get_by_role("button", name=call_label("Nova")).click()
        agent.accept(agent.invitation_within(felix, INVITATION_WITHIN_SECONDS))
        expect(plate_of(olga, 2)).to_contain_text("Nova")

        pill(olga).click()
        olga.get_by_role("button", name=ask_to_leave_label("Nova")).click()

        for person in (felix, olga):
            expect(plate_of(person, 2)).to_contain_text(SEAT_FREE)
            expect(plate_of(person, 2)).not_to_contain_text("Nova")
    finally:
        agent.close()


def test_a_call_the_page_sends_while_the_test_waits_for_the_agent_still_reaches_the_server(
    caller: Page,
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
) -> None:
    open_new_table(caller, e2e_server)
    agent = ListeningAgent(e2e_server, member_of(caller).account.id, "Raphael", "agent-subject-raphael")
    try:
        expect(pill(caller)).to_be_visible()
        pill(caller).click()
        caller.evaluate(DELAY_FETCHES)
        caller.get_by_role("button", name=call_label("Raphael")).click()
        agent.accept(agent.invitation_within(caller, INVITATION_WITHIN_SECONDS))
        expect(caller.locator(".chair:has-text('Raphael')")).to_have_count(1)
    finally:
        agent.close()


def test_two_agents_of_one_owner_are_called_one_after_the_other_and_both_sit(
    caller: Page,
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
) -> None:
    open_new_table(caller, e2e_server)
    owner = member_of(caller).account.id
    mozart = ListeningAgent(e2e_server, owner, "Mozart", "agent-subject-mozart")
    leonardo = ListeningAgent(e2e_server, owner, "Leonardo", "agent-subject-leonardo-two")
    try:
        for name, agent in (("Mozart", mozart), ("Leonardo", leonardo)):
            expect(pill(caller)).to_be_visible()
            pill(caller).click()
            caller.get_by_role("button", name=call_label(name)).click()
            seated = agent.accept(agent.invitation_within(caller, INVITATION_WITHIN_SECONDS))
            expect(caller.locator(f".chair:has-text('{name}')")).to_have_count(1)
            pill(caller).click()
        expect(caller.locator(".chair .plate:has(.ai-mark)")).to_have_count(2)
        for agent in (mozart, leonardo):
            window = agent.window(seated["place"]["id"])
            assert len(agent.listed()) == 3
            assert [line["kind"] for line in window["entries"]] == ["deal"]
    finally:
        mozart.close()
        leonardo.close()


@pytest.mark.usefixtures("realm_reusing_refresh_tokens")
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_call_the_agent_answers_busy_tells_the_caller_so_on_the_row_and_no_one_else(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict,
) -> None:
    felix = record_page_errors(
        open_person(username="felix-hears-busy", groups=(AGENT_ADDERS_GROUP,), **form_factor), page_errors
    )
    path = open_new_table(felix, e2e_server)
    guests = [
        record_page_errors(open_person(username=f"guest-{seat}-keeps-busy", **DESKTOP), page_errors) for seat in (2, 3)
    ]
    agent = ListeningAgent(e2e_server, member_of(felix).account.id, "Michelangelo", "agent-subject-michelangelo")
    try:
        pill(felix).click()
        felix.get_by_role("button", name=call_label("Michelangelo")).click()
        invitation = agent.invitation_within(felix, INVITATION_WITHIN_SECONDS)
        for seat, guest in zip((2, 3), guests, strict=True):
            watch(guest, e2e_server, path)
            sit_in(guest, seat)
            expect(plate_of(felix, seat)).not_to_contain_text(SEAT_FREE)

        agent.accept_refused(invitation)

        expect(felix.get_by_text(BUSY)).to_be_visible()
        expect(pill(guests[0])).to_have_count(0)
    finally:
        agent.close()


@pytest.fixture
def server_without_agents(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    # A server of its own: the agents of the other tests keep their roster entries for a few seconds after they stop.
    with skat_on_new_database(tmp_path_factory) as server:
        yield server


def test_the_list_says_so_when_no_agent_is_reachable(
    open_person: Callable[..., Page], server_without_agents: RunningServer, page_errors: list[str]
) -> None:
    server = server_without_agents
    person = record_page_errors(
        open_person(username="felix-alone", server=server, groups=(AGENT_ADDERS_GROUP,), **DESKTOP), page_errors
    )
    open_new_table(person, server)

    expect(pill(person)).to_be_visible()
    pill(person).click()

    expect(person.get_by_text(EMPTY)).to_be_visible()
    # The page leaves before its server stops, so its stream's reconnect is no failed request.
    person.goto("about:blank")
