"""The roster offers one entry per agent that listens under the issuer on its standing and has a record, carrying the
record's name and owner and a key derived from the session secret, the same on every pod. A call writes or refreshes
the agent's record and goes on when the write fails. A place store or record store that does not answer lists no agent
until it answers again.
"""

import asyncio
import base64

import pytest
from agents.mcp_server import PlaceStoreError
from agents.tools import Principal
from webauth.ports import AgentFacts

from skat.web.calling import AgentRoster
from tests.support.in_memory_agent_records import InMemoryAgentRecords

ISSUER = "an-issuer"
NOVA = Principal(iss=ISSUER, sub="agent-nova")
BACH = Principal(iss=ISSUER, sub="agent-bach")
SIGNING_KEY = b"a-session-secret-of-the-test"
BYTES_OF_A_KEY = 16


class Listeners:
    """The place store as the roster reads it: who listens now, or a store that does not answer."""

    def __init__(self, *listening):
        self.listening = frozenset(listening)
        self.fails = False

    async def __call__(self, uri):
        if self.fails:
            raise PlaceStoreError("the store does not answer")
        return self.listening


@pytest.fixture
def listeners():
    return Listeners(NOVA)


@pytest.fixture
def records():
    return InMemoryAgentRecords()


def roster_of(listeners, records, *, signing_key=SIGNING_KEY):
    return AgentRoster(listeners, ISSUER, records, signing_key)


def entries_of(roster):
    return asyncio.run(roster.entries())


def heard(roster, principal, facts):
    asyncio.run(roster.heard(principal.sub, facts))


class TestAnEntryExistsWhileTheAgentListensAndItsRecordStands:
    def test_the_entry_carries_the_name_and_owner_of_the_record(self, listeners, records):
        roster = roster_of(listeners, records)
        heard(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))

        entry = entries_of(roster)[NOVA.sub]

        assert (entry.name, entry.owner) == ("Nova", "owner-felix")

    def test_a_listener_without_a_record_has_no_entry(self, listeners, records):
        assert entries_of(roster_of(listeners, records)) == {}

    def test_a_record_without_a_listener_has_no_entry(self, records):
        roster = roster_of(Listeners(), records)
        heard(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))

        assert entries_of(roster) == {}

    def test_a_listener_under_another_issuer_has_no_entry(self, records):
        stranger = Principal(iss="another-issuer", sub=NOVA.sub)
        roster = roster_of(Listeners(stranger), records)
        heard(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))

        assert entries_of(roster) == {}

    def test_a_later_call_replaces_the_name_and_owner_and_keeps_the_key(self, listeners, records):
        roster = roster_of(listeners, records)
        heard(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))
        key = entries_of(roster)[NOVA.sub].key

        heard(roster, NOVA, AgentFacts(owner="owner-anna", name="Nova2"))

        entry = entries_of(roster)[NOVA.sub]
        assert (entry.owner, entry.name, entry.key) == ("owner-anna", "Nova2", key)

    def test_two_agents_of_one_owner_with_one_name_are_two_entries(self, records):
        roster = roster_of(Listeners(NOVA, BACH), records)
        for principal in (NOVA, BACH):
            heard(roster, principal, AgentFacts(owner="owner-felix", name="Mozart"))

        assert set(entries_of(roster)) == {NOVA.sub, BACH.sub}


class TestAStoreThatDoesNotAnswer:
    def test_a_place_store_that_does_not_answer_lists_no_agent_until_it_answers(self, listeners, records):
        roster = roster_of(listeners, records)
        heard(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))
        listeners.fails = True
        while_down = entries_of(roster)
        listeners.fails = False

        assert (while_down, set(entries_of(roster))) == ({}, {NOVA.sub})

    def test_a_record_store_that_does_not_answer_lists_no_agent_until_it_answers(self, listeners, records):
        roster = roster_of(listeners, records)
        heard(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))
        records.fails_reads = True
        while_down = entries_of(roster)
        records.fails_reads = False

        assert (while_down, set(entries_of(roster))) == ({}, {NOVA.sub})


class TestAFailedWriteOfTheRecord:
    def test_is_not_raised_and_the_agent_is_listed_once_a_write_succeeds(self, listeners, records):
        roster = roster_of(listeners, records)
        records.fails_writes = True
        heard(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))
        while_failing = entries_of(roster)
        records.fails_writes = False
        heard(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))

        assert (while_failing, set(entries_of(roster))) == ({}, {NOVA.sub})


class TestARowKeyIsDerivedFromTheSessionSecret:
    def test_every_pod_with_the_secret_derives_the_same_key(self, listeners, records):
        one_pod = roster_of(listeners, records)
        another_pod = roster_of(listeners, records)

        assert one_pod.key_of(NOVA.sub) == another_pod.key_of(NOVA.sub)

    def test_another_secret_or_another_account_derives_another_key(self, listeners, records):
        roster = roster_of(listeners, records)

        keys = {
            roster.key_of(NOVA.sub),
            roster.key_of(BACH.sub),
            roster_of(listeners, records, signing_key=b"another-secret").key_of(NOVA.sub),
        }

        assert len(keys) == 3

    def test_the_key_names_no_account_and_keeps_at_least_128_bits(self, listeners, records):
        key = AgentRoster(listeners, ISSUER, records, SIGNING_KEY).key_of(NOVA.sub)

        assert NOVA.sub not in key
        assert len(base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))) >= BYTES_OF_A_KEY

    def test_an_entry_has_the_key_of_its_account(self, listeners, records):
        roster = roster_of(listeners, records)
        heard(roster, NOVA, AgentFacts(owner="owner-felix", name="Nova"))

        assert entries_of(roster)[NOVA.sub].key == roster.key_of(NOVA.sub)
