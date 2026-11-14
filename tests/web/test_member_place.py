"""A table is a member place at /mcp: an agent reads its standing, is invited to a table and accepts the invitation."""

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from agents.member import LEASE_SECONDS, STANDING_URI, AcceptInvitationRefusal
from starlette.concurrency import run_in_threadpool

from skat.table.member_place import MemberRefusal
from skat.table.records import TableId
from skat.web.mcp import MCP_GROUP
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.support.calls import call_facts
from tests.support.played_game import after_the_first_game
from tests.web.support.agent import UPDATED, Agent
from tests.web.support.presence import HOLD_SECONDS
from tests.web.support.skat import FakeTime, Skat, stored, streams_of

OTHER_AGENT_SUBJECT = "other-agent-subject"
INVITATION_SECONDS = 600
STALE = {"refused": "stale_invitation"}
SPONSOR_AWAY = {"refused": "sponsor_away"}
BUSY = {"refused": "busy"}


@pytest.fixture
def time():
    return FakeTime()


@pytest.fixture
def skat(hold, issuer, time):
    skat = Skat(
        lambda: hold, issuer_transports=issuer.transports, chair_clock=time.clock, chair_scheduler=time, now=time.moment
    )
    with skat.client:
        yield skat


@pytest.fixture
def owner(skat):
    """The person the agent works for: their headers and account."""
    return skat.member()


@pytest.fixture
def agent(skat, issuer, owner):
    return Agent(skat, issuer, agent_owner=owner[1].id)


@pytest.fixture
def table_id(skat, owner):
    """A table the owner opened and sits at, with no stream open."""
    created = skat.create(owner[0])
    skat.client.cookies.clear()
    return created.json()["id"]


def a_person(skat, issuer):
    """A person's own token at /mcp: the account is a person's and the token carries no agent facts."""
    return Agent(skat, issuer, skat.member()[1].id, agent_owner=None, agent_name=None, groups=[MCP_GROUP])


@pytest.fixture
def invite(skat, time):
    """Writes an invitation through the service the app wired, on its event loop's worker."""

    def write_invitation(agent, table_id, owner, *, inviter=None, lasting=INVITATION_SECONDS):
        facts = call_facts(agent.subject, owner[1].id, (inviter or owner)[1].id)

        async def write():
            return await run_in_threadpool(
                skat.tables.invite_agent, TableId(table_id), facts, timedelta(seconds=lasting)
            )

        return skat.client.portal.call(write)

    return write_invitation


def standing_of(agent):
    return json.loads(agent.standing())["standings"]


def at_the_table(skat, table_id, *people):
    return streams_of(skat, table_id, [(headers, None) for headers, _ in people])


def chairs_of(skat, table_id):
    return [
        None if chair.occupant is None else (chair.occupant.display_name, chair.occupant.kind.value)
        for chair in skat.store.tables[table_id].chairs
    ]


class TestTheStandingIsAResource:
    def test_an_agent_lists_and_reads_its_standing_which_is_empty_at_first(self, agent):
        assert agent.listed_resources() == [STANDING_URI]
        assert standing_of(agent) == []

    def test_a_persons_token_lists_nothing_and_reads_the_standing_as_an_unknown_resource(self, skat, issuer):
        person = a_person(skat, issuer)

        answer = person.request("resources/read", {"uri": STANDING_URI})

        assert person.listed_resources() == []
        assert answer.json()["error"]["message"] == "Unknown resource"

    def test_a_token_without_agent_facts_for_a_stored_agent_lists_nothing_and_reads_an_unknown_resource(
        self, skat, issuer, agent
    ):
        agent.admitted()
        person_token = Agent(skat, issuer, agent.subject, agent_owner=None, agent_name=None, groups=[MCP_GROUP])

        answer = person_token.request("resources/read", {"uri": STANDING_URI})

        assert person_token.listed_resources() == []
        assert answer.json()["error"]["message"] == "Unknown resource"

    def test_another_agent_reads_a_standing_that_holds_none_of_the_first_agents_tables(
        self, invite, skat, issuer, agent, owner, table_id
    ):
        invite(agent, table_id, owner)
        other = Agent(skat, issuer, OTHER_AGENT_SUBJECT, agent_owner=owner[1].id, agent_name="Bach")

        assert [standing["state"] for standing in standing_of(agent)] == ["invited"]
        assert standing_of(other) == []

    def test_no_answer_names_the_owner_or_the_inviter(self, invite, skat, agent, owner, table_id):
        inviter = skat.member()
        offer = invite(agent, table_id, owner, inviter=inviter)
        shown = [agent.standing(), agent.accept(table_id, offer, epoch=offer.epoch + 1).text]
        shown.append(agent.accept(table_id, offer).text)
        with at_the_table(skat, table_id, owner):
            shown.append(agent.accept(table_id, offer).text)
        shown.append(agent.standing())

        assert not [text for text in shown if owner[1].id in text or inviter[1].id in text]


class TestAnInvitationIsAcceptedAtOnce:
    def test_a_listening_agent_is_told_of_the_invitation_and_of_its_chair_and_reads_each(
        self, invite, skat, agent, owner, table_id
    ):
        with agent.listening() as frames, at_the_table(skat, table_id, owner):
            offer = invite(agent, table_id, owner)
            assert next(frames)["method"] == UPDATED
            invited = standing_of(agent)

            accepted = agent.accept(table_id, offer)
            assert next(frames)["method"] == UPDATED
            seated = standing_of(agent)

        assert [(standing["state"], standing["place"]["id"]) for standing in invited] == [("invited", table_id)]
        assert (invited[0]["invitation"]["id"], invited[0]["invitation"]["epoch"]) == (offer.id, offer.epoch)
        assert not accepted.is_error, accepted.text
        assert [(standing["state"], standing["invitation"]) for standing in seated] == [("active", None)]
        assert chairs_of(skat, table_id)[1] == ("Mozart", "agent")

    def test_an_owner_who_only_watches_the_open_table_is_present(self, invite, skat, agent, owner, table_id):
        skat.stand(owner[0], table_id)
        offer = invite(agent, table_id, owner)

        with at_the_table(skat, table_id, owner):
            answer = agent.accept(table_id, offer)

        assert not answer.is_error, answer.text
        assert chairs_of(skat, table_id) == [("Mozart", "agent"), None, None]

    def test_the_agent_stays_a_member_when_its_owner_leaves_and_leaves_by_standing_up(
        self, invite, skat, agent, owner, table_id
    ):
        offer = invite(agent, table_id, owner)
        with at_the_table(skat, table_id, owner):
            agent.accept(table_id, offer)
        skat.client.cookies.clear()

        assert [standing["state"] for standing in standing_of(agent)] == ["active"]
        assert not agent.stand_up(table_id).is_error
        assert standing_of(agent) == []
        assert not agent.sit_down(table_id, 2).is_error
        assert [standing["state"] for standing in standing_of(agent)] == ["active"]

    def test_the_accept_that_fills_the_third_chair_deals_and_the_tables_streams_see_the_hand(
        self, invite, skat, agent, owner, table_id
    ):
        visitor = skat.member()
        skat.sit(visitor[0], table_id, 2)
        skat.client.cookies.clear()
        offer = invite(agent, table_id, owner)

        with at_the_table(skat, table_id, owner) as (owner_messages,):
            answer = agent.accept(table_id, offer)
            dealt = next(owner_messages)

        assert not answer.is_error, answer.text
        assert dealt["hand"] is not None
        assert skat.store.tables[table_id].dealer is not None
        assert table_id in skat.store.last_played_at

    def test_an_accept_while_a_games_result_is_pending_counts_the_agent_ready_and_deals_when_all_are(
        self, invite, skat, agent, owner, table_id
    ):
        visitor, third = skat.member(), skat.member()
        skat.sit(visitor[0], table_id, 2)
        skat.sit(third[0], table_id, 3)
        skat.client.cookies.clear()
        skat.store.tables[table_id] = after_the_first_game(skat.store.tables[table_id], 1, 2)
        skat.store.tables[table_id] = _with_the_third_chair_free(skat.store.tables[table_id])
        offer = invite(agent, table_id, owner)

        with at_the_table(skat, table_id, owner, visitor):
            answer = agent.accept(table_id, offer)

        assert not answer.is_error, answer.text
        assert skat.store.tables[table_id].hand is not None

    def test_an_agent_that_sits_by_the_link_or_opens_a_table_reads_it_active_and_is_told(self, skat, agent, table_id):
        with agent.listening() as frames:
            agent.sit_down(table_id, 2)
            assert next(frames)["method"] == UPDATED
            opened = agent.offered_every_tool().open_table().json()["id"]
            assert next(frames)["method"] == UPDATED

        assert {(standing["state"], standing["place"]["id"]) for standing in standing_of(agent)} == {
            ("active", table_id),
            ("active", opened),
        }


def _with_the_third_chair_free(table):
    chairs = tuple(replace(chair, occupant=None, ready=False) if chair.seat == 3 else chair for chair in table.chairs)
    return replace(table, chairs=chairs)


class TestAnAcceptThatIsStale:
    """An accept that no longer matches an open invitation is refused as stale."""

    @pytest.mark.parametrize(
        "changes",
        [
            pytest.param({"invitation": "another-id"}, id="another-id"),
            pytest.param({"epoch": 1}, id="another-epoch"),
            pytest.param({"place": {"kind": "call", "id": "x"}}, id="another-place-kind"),
            pytest.param({"epoch": -1}, id="malformed-arguments"),
        ],
    )
    def test_when_the_arguments_do_not_name_the_open_invitation(self, invite, skat, agent, owner, table_id, changes):
        offer = invite(agent, table_id, owner)
        before = stored(skat)

        with at_the_table(skat, table_id, owner):
            answer = agent.accept(table_id, offer, **changes)

        assert (answer.is_error, answer.json()) == (True, STALE)
        assert stored(skat) == before
        assert [standing["state"] for standing in standing_of(agent)] == ["invited"]

    def test_when_it_comes_a_second_time_after_seating(self, invite, skat, agent, owner, table_id):
        offer = invite(agent, table_id, owner)
        with at_the_table(skat, table_id, owner):
            agent.accept(table_id, offer)
            again = agent.accept(table_id, offer)

        assert (again.is_error, again.json()) == (True, STALE)
        assert chairs_of(skat, table_id)[1] == ("Mozart", "agent")

    def test_after_the_expiry_on_the_services_clock_and_a_new_invitation_then_works(
        self, invite, skat, time, agent, owner, table_id
    ):
        offer = invite(agent, table_id, owner)
        skat.client.portal.call(time.advance, INVITATION_SECONDS)

        with at_the_table(skat, table_id, owner):
            answer = agent.accept(table_id, offer)
        listed = standing_of(agent)
        fresh = invite(agent, table_id, owner)

        assert (answer.is_error, answer.json(), listed) == (True, STALE, [])
        assert fresh.id != offer.id

    def test_when_another_agent_or_a_person_accepts(self, invite, skat, issuer, agent, owner, table_id):
        offer = invite(agent, table_id, owner)
        before = stored(skat)
        other = Agent(skat, issuer, OTHER_AGENT_SUBJECT, agent_owner=owner[1].id, agent_name="Bach")
        person = a_person(skat, issuer)

        with at_the_table(skat, table_id, owner):
            answers = [each.accept(table_id, offer) for each in (other, person)]

        assert [(answer.is_error, answer.json()) for answer in answers] == [(True, STALE)] * 2
        assert stored(skat) == before

    def test_when_the_owner_of_the_token_is_not_the_owner_of_the_invitation(
        self, invite, skat, issuer, agent, owner, table_id
    ):
        offer = invite(agent, table_id, owner)
        deputy = Agent(skat, issuer, agent.subject, agent_owner=skat.member()[1].id)

        with at_the_table(skat, table_id, owner):
            answer = deputy.accept(table_id, offer)

        assert (answer.is_error, answer.json()) == (True, STALE)

    def test_when_the_agent_sat_down_by_the_link_before_it_accepted(self, invite, skat, agent, owner, table_id):
        offer = invite(agent, table_id, owner)
        agent.sit_down(table_id, 3)

        with at_the_table(skat, table_id, owner):
            answer = agent.accept(table_id, offer)

        assert (answer.is_error, answer.json()) == (True, STALE)
        assert chairs_of(skat, table_id) == [
            (skat.stores.accounts.get(owner[1].id).username, "person"),
            None,
            ("Mozart", "agent"),
        ]
        assert [standing["state"] for standing in standing_of(agent)] == ["active"]


class TestAnAcceptRefusedAndTheInvitationEnds:
    @pytest.mark.parametrize("seated_and_away", [False, True], ids=["owner-left-the-table", "owner-seated-but-away"])
    def test_sponsor_away_without_a_stream_of_the_owner_on_the_table(
        self, invite, skat, agent, owner, table_id, seated_and_away
    ):
        if not seated_and_away:
            skat.stand(owner[0], table_id)
        offer = invite(agent, table_id, owner)
        before = skat.store.tables[table_id]

        answer = agent.accept(table_id, offer)

        assert (answer.is_error, answer.json()) == (True, SPONSOR_AWAY)
        assert skat.store.tables[table_id] == before
        assert standing_of(agent) == []

    def test_busy_when_no_chair_is_free(self, invite, skat, agent, owner, table_id):
        offer = invite(agent, table_id, owner)
        for seat in (2, 3):
            skat.sit(skat.member()[0], table_id, seat)
        skat.client.cookies.clear()
        before = skat.store.tables[table_id]

        with at_the_table(skat, table_id, owner):
            answer = agent.accept(table_id, offer)

        assert (answer.is_error, answer.json()) == (True, BUSY)
        assert skat.store.tables[table_id] == before
        assert standing_of(agent) == []


class TestTheStandingFollowsTheChair:
    @pytest.fixture
    def seated(self, skat, agent, table_id):
        agent.sit_down(table_id, 2)

    @pytest.mark.usefixtures("seated")
    def test_the_agents_chair_stays_during_the_hold_and_is_freed_after_it(self, skat, time, agent, table_id):
        skat.client.portal.call(time.advance, LEASE_SECONDS + 1)
        assert [standing["state"] for standing in standing_of(agent)] == ["active"]

        skat.client.portal.call(time.advance, LEASE_SECONDS + HOLD_SECONDS + 1)

        assert chairs_of(skat, table_id)[1] is None
        assert standing_of(agent) == []

    @pytest.mark.usefixtures("seated")
    def test_a_listening_agent_whose_lease_lapsed_is_told_when_the_hold_frees_its_chair(
        self, skat, time, agent, table_id
    ):
        with agent.listening() as frames:
            skat.client.portal.call(time.advance, LEASE_SECONDS + HOLD_SECONDS + 1)
            freed = next(frames)
            after = standing_of(agent)

        assert freed["method"] == UPDATED
        assert chairs_of(skat, table_id)[1] is None
        assert after == []

    def test_the_end_of_the_table_leaves_an_invited_agent_told_and_with_no_table(
        self, invite, skat, time, agent, owner, table_id
    ):
        skat.stand(owner[0], table_id)
        skat.client.cookies.clear()
        invite(agent, table_id, owner)

        with agent.listening() as frames:
            skat.client.portal.call(time.advance, DEFAULT_EMPTY_TABLE_SECONDS + 1)
            ended = next(frames)
            after = standing_of(agent)

        assert ended["method"] == UPDATED
        assert after == []

    def test_an_agent_whose_lease_lapses_during_a_hand_stays_a_member(self, skat, time, middlehand_auction, agent):
        skat.client.portal.call(time.advance, LEASE_SECONDS + HOLD_SECONDS + 1)

        assert [standing["state"] for standing in standing_of(agent)] == ["active"]
        assert skat.store.tables[middlehand_auction.table_id].hand is not None


class TestAFailingStore:
    def test_fails_the_accept_loud_with_the_fronts_fixed_failure(
        self, invite, skat, agent, owner, table_id, monkeypatch
    ):
        offer = invite(agent, table_id, owner)

        def fail(*_):
            raise ConnectionError("lost the store")

        monkeypatch.setattr(skat.store, "locked_book_entry", fail)
        answer = agent.accept(table_id, offer)

        assert (answer.is_error, answer.text) == (True, "the tool failed")


def test_every_refusal_the_table_gives_is_one_the_library_knows():
    assert {refusal.value for refusal in MemberRefusal} <= {refusal.value for refusal in AcceptInvitationRefusal}
