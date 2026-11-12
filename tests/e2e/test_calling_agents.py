"""A member of the calling group opens the pill „Agenten“, taps „Rufen“ on an agent's row, and the agent sits."""

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from skat.web.calling import AGENT_ADDERS_GROUP
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.listening_agent import ListeningAgent
from tests.e2e.support.people import DESKTOP, WIDTHS
from tests.e2e.support.server import skat_on_new_database
from tests.e2e.support.tables import open_new_table, plate_of, watch

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from playwright.sync_api import Page

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

PILL = text(SOURCE_LANGUAGE, "agents.pill")
CALLING = text(SOURCE_LANGUAGE, "agents.calling")
EMPTY = text(SOURCE_LANGUAGE, "agents.empty")
AI_MARK = "AI"
INVITATION_WITHIN_SECONDS = 15


def pill(person: Page):
    return person.get_by_role("button", name=PILL)


def call_label(name: str) -> str:
    return text(SOURCE_LANGUAGE, "agents.callLabel").replace("{name}", name)


def sits_note(name: str) -> str:
    return text(SOURCE_LANGUAGE, "table.agentSits").replace("{name}", name)


@pytest.fixture
def realm_reusing_refresh_tokens(e2e_server: RunningServer) -> Iterator[None]:
    # The realm lets a refresh token be used again, so overlapping reads of one session both succeed.
    e2e_server.issuer.reuses_refresh_tokens = True
    yield
    e2e_server.issuer.reuses_refresh_tokens = False


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
        agent.accept(agent.invitation_within(INVITATION_WITHIN_SECONDS))
        for person in (felix, anna):
            expect(plate_of(person, 2)).to_contain_text("Leonardo")
            expect(plate_of(person, 2)).to_contain_text(AI_MARK)
        expect(felix.get_by_text(sits_note("Leonardo"))).to_be_visible()
        expect(pill(anna)).to_have_count(0)
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
            agent.accept(agent.invitation_within(INVITATION_WITHIN_SECONDS))
            expect(caller.locator(f".chair:has-text('{name}')")).to_have_count(1)
            pill(caller).click()
        expect(caller.locator(".chair .plate:has(.ai-mark)")).to_have_count(2)
    finally:
        mozart.close()
        leonardo.close()


def test_the_list_says_so_when_no_agent_is_reachable(
    open_person: Callable[..., Page], tmp_path_factory: pytest.TempPathFactory, page_errors: list[str]
) -> None:
    # A server of its own: the agents of the other tests keep their roster entries for a few seconds after they stop.
    with skat_on_new_database(tmp_path_factory) as server:
        person = record_page_errors(
            open_person(username="felix-alone", server=server, groups=(AGENT_ADDERS_GROUP,), **DESKTOP), page_errors
        )
        open_new_table(person, server)

        expect(pill(person)).to_be_visible()
        pill(person).click()

        expect(person.get_by_text(EMPTY)).to_be_visible()
        # The page leaves before its server stops, so its stream's reconnect is no failed request.
        person.goto("about:blank")
