"""The roster holds an agent exactly while it listens on its standing, under what its own token says of it."""

import asyncio
from contextlib import contextmanager

import pytest
from agents.mcp_server.listen import ResourceChanges
from agents.member import STANDING_URI, PlaceRef, place_view_uri
from agents.tools import Principal
from webauth.ports import AgentFacts

from skat.web.calling import AgentRoster
from skat.web.mcp import token_carries_agent_facts

NOVA = Principal(iss="an-issuer", sub="agent-nova")
BACH = Principal(iss="an-issuer", sub="agent-bach")


@contextmanager
def token_of(facts):
    marker = token_carries_agent_facts.set(facts)
    try:
        yield
    finally:
        token_carries_agent_facts.reset(marker)


def starts_to_listen(roster, principal, facts, uri=STANDING_URI):
    with token_of(facts):
        roster.listening_changed(principal, uri, True)


def listens_once_and_closes(roster, principal, facts, *, after_close):
    """The agent's one listen on its standing through the library's own bookkeeping; `after_close` runs once the
    stream has ended, before the loop has run anything the library scheduled for the end of the allowance.
    """

    async def listen_then_close():
        changes = ResourceChanges(roster.listening_changed)
        with changes.opened(principal) as stream, token_of(facts):
            changes.acknowledged(principal, stream, [STANDING_URI], tools=False)
        after_close()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(listen_then_close())


@pytest.fixture
def roster():
    return AgentRoster()


class TestAnEntryExistsWhileTheAgentListens:
    def test_an_agent_that_starts_to_listen_has_an_entry_with_the_name_and_owner_of_its_token(self, roster):
        starts_to_listen(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))

        entry = roster.entries()[NOVA.sub]

        assert (entry.name, entry.owner) == ("Nova", "owner-felix")

    def test_the_entry_is_dropped_when_the_agent_stops_listening(self, roster):
        starts_to_listen(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))

        roster.listening_changed(NOVA, STANDING_URI, False)

        assert roster.entries() == {}

    def test_stopping_to_listen_without_an_entry_changes_nothing(self, roster):
        roster.listening_changed(NOVA, STANDING_URI, False)

        assert roster.entries() == {}

    def test_a_listen_with_no_agent_facts_makes_no_entry(self, roster):
        starts_to_listen(roster, NOVA, None)

        assert roster.entries() == {}

    def test_a_listen_on_a_resource_other_than_the_standing_makes_no_entry(self, roster):
        starts_to_listen(
            roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"), place_view_uri(PlaceRef(kind="table", id="t"))
        )

        assert roster.entries() == {}

    def test_each_agent_has_its_own_key_that_names_no_account(self, roster):
        starts_to_listen(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))
        starts_to_listen(roster, BACH, AgentFacts(owner="owner-felix", name="Bach"))

        keys = {account: entry.key for account, entry in roster.entries().items()}

        assert len(set(keys.values())) == 2
        assert all(account not in key for account, key in keys.items())


class TestACallOfAnAgentWithFacts:
    def test_keeps_the_entry_and_its_key_while_the_facts_stay_the_same(self, roster):
        facts = AgentFacts(owner="owner-felix", name="Nova")
        starts_to_listen(roster, NOVA, facts)
        key = roster.entries()[NOVA.sub].key

        roster.heard(NOVA.sub, facts)

        assert roster.entries()[NOVA.sub].key == key

    def test_replaces_the_name_and_owner_and_keeps_the_key_when_a_newer_token_says_otherwise(self, roster):
        starts_to_listen(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))
        key = roster.entries()[NOVA.sub].key

        roster.heard(NOVA.sub, AgentFacts(owner="owner-anna", name="Nova2"))

        entry = roster.entries()[NOVA.sub]
        assert (entry.owner, entry.name, entry.key) == ("owner-anna", "Nova2", key)

    def test_makes_no_entry_for_an_agent_that_does_not_listen(self, roster):
        roster.heard(NOVA.sub, AgentFacts(owner="owner-felix", name="Nova"))

        assert roster.entries() == {}


class TestAnEntryOutlivesTheEndOfItsListenByTheLibrarysAllowance:
    def test_the_entry_stays_when_the_listen_ends_and_is_dropped_once_the_allowance_passed(self, roster, monkeypatch):
        monkeypatch.setattr("agents.mcp_server.listen.LISTEN_ALLOWANCE_SECONDS", 0)
        held_at_the_end = []

        listens_once_and_closes(
            roster,
            NOVA,
            AgentFacts(owner="owner-felix", name="Nova"),
            after_close=lambda: held_at_the_end.append(set(roster.entries())),
        )

        assert (held_at_the_end, roster.entries()) == ([{NOVA.sub}], {})

    def test_two_agents_of_one_owner_with_one_name_hold_one_entry_each(self, roster):
        facts = AgentFacts(owner="owner-felix", name="Mozart")
        starts_to_listen(roster, NOVA, facts)
        starts_to_listen(roster, BACH, facts)

        assert {(entry.name, entry.owner) for entry in roster.entries().values()} == {("Mozart", "owner-felix")}
        assert set(roster.entries()) == {NOVA.sub, BACH.sub}


class TestAnAgentKeepsOneKey:
    def test_the_key_of_an_account_is_made_at_first_need_and_names_no_account(self, roster):
        key = roster.key_of(NOVA.sub)

        assert (roster.key_of(NOVA.sub) == key, NOVA.sub in key, roster.key_of(BACH.sub) != key) == (True, False, True)

    def test_an_entry_uses_the_key_the_account_already_has(self, roster):
        key = roster.key_of(NOVA.sub)

        starts_to_listen(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))

        assert roster.entries()[NOVA.sub].key == key

    def test_the_key_stays_when_the_agent_stops_listening_and_listens_again(self, roster):
        starts_to_listen(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))
        key = roster.entries()[NOVA.sub].key

        roster.listening_changed(NOVA, STANDING_URI, False)
        starts_to_listen(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))

        assert roster.entries()[NOVA.sub].key == key
