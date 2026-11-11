"""The roster holds an agent exactly while it listens on its standing, under what its own token says of it."""

from contextlib import contextmanager

import pytest
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
        assert {roster.account_of(key) for key in keys.values()} == {NOVA.sub, BACH.sub}

    def test_a_key_that_no_entry_holds_names_no_account(self, roster):
        assert roster.account_of("a-key-no-entry-holds") is None


class TestACallOfAnAgentWithFacts:
    def test_keeps_the_entry_and_its_key_while_the_facts_stay_the_same(self, roster):
        facts = AgentFacts(owner="owner-felix", name="Nova")
        starts_to_listen(roster, NOVA, facts)
        key = roster.entries()[NOVA.sub].key

        roster.heard(NOVA.sub, facts)

        assert roster.entries()[NOVA.sub].key == key

    def test_replaces_the_name_owner_and_key_when_a_newer_token_says_otherwise(self, roster):
        starts_to_listen(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))
        key = roster.entries()[NOVA.sub].key

        roster.heard(NOVA.sub, AgentFacts(owner="owner-anna", name="Nova"))

        entry = roster.entries()[NOVA.sub]
        assert (entry.owner, entry.key != key) == ("owner-anna", True)

    def test_makes_no_entry_for_an_agent_that_does_not_listen(self, roster):
        roster.heard(NOVA.sub, AgentFacts(owner="owner-felix", name="Nova"))

        assert roster.entries() == {}
