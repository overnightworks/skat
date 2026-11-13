"""The invitation book against Postgres: the accept's one-chair race, the book across a restart and the retention."""

import random
import threading
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from skat.store.tables import PostgresTableTransactions
from skat.table.member_place import ENDED_CALL_KEPT, Acceptance, CallOutcome, MemberRefusal, MembershipState
from skat.table.records import Actor, CreateTable, OccupantKind, SitDown, TableId
from skat.table.service import TableService
from tests.support.calls import call_facts
from tests.support.faulty_tables import BothReadBeforeEitherWrites

pytestmark = pytest.mark.postgres

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")
MOZART = Actor(account_id="account-mozart", display_name="Mozart", kind=OccupantKind.AGENT)
BACH = Actor(account_id="account-bach", display_name="Bach", kind=OccupantKind.AGENT)
START = datetime(2026, 11, 1, 12, tzinfo=UTC)
LASTING = timedelta(hours=1)
LATER = START + LASTING
OWNER_AT_THE_TABLE = frozenset({OPENER.account_id})


@pytest.fixture
def service(transactions):
    return TableService(transactions, random_source=random.Random(8), now=lambda: START)  # noqa: S311 - seeded


@pytest.fixture
def table_id(service):
    table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
    service.sit(VISITOR, SitDown("command-ben", table_id, 2), frozenset())
    return table_id


def invite(service, table_id, agent):
    facts = call_facts(agent.account_id, OPENER.account_id)
    return service.invite_agent(TableId(table_id), facts, LASTING)


def book_row(engine, agent):
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT epoch, invitation_id, owner_account, inviter_account, ended_outcome FROM member_book"
                " WHERE agent_account = :a"
            ),
            {"a": agent.account_id},
        ).one()


def accept(service, table_id, agent, offer):
    return service.accept_invitation(
        agent, OPENER.account_id, Acceptance(table_id, offer.id, offer.epoch), OWNER_AT_THE_TABLE
    )


class TestTwoAcceptsForTheLastChair:
    def test_seat_exactly_one_and_refuse_the_other_busy(self, service, engine, table_id):
        offers = {agent: invite(service, table_id, agent) for agent in (MOZART, BACH)}
        racing = TableService(BothReadBeforeEitherWrites(PostgresTableTransactions(engine), 2), now=lambda: START)
        results = {}

        def run(agent):
            results[agent.display_name] = accept(racing, table_id, agent, offers[agent])

        threads = [threading.Thread(target=run, args=(agent,)) for agent in offers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        winners = [agent for agent in offers if results[agent.display_name].refusal is None]
        losers = [agent for agent in offers if results[agent.display_name].refusal is not None]
        assert [results[agent.display_name].refusal for agent in losers] == [MemberRefusal.BUSY]
        assert len(winners) == 1
        chairs = service.view(OPENER, table_id, frozenset()).chairs
        assert [chair.occupant_name for chair in chairs] == ["Anna", "Ben", winners[0].display_name]
        assert [standing.state for standing in service.standings_of(winners[0].account_id)] == [MembershipState.ACTIVE]
        assert service.standings_of(losers[0].account_id) == ()


class TestTheBookAcrossARestart:
    def test_keeps_an_open_invitation_a_held_chair_and_the_epoch(self, service, engine, transactions, table_id):
        offer = invite(service, table_id, MOZART)
        service.sit(BACH, SitDown("command-bach", table_id, 3), frozenset())
        with engine.begin() as connection:
            connection.execute(text("UPDATE member_book SET epoch = 4 WHERE agent_account = 'account-mozart'"))

        restarted = TableService(transactions, now=lambda: START)

        shown = restarted.standings_of(MOZART.account_id)
        assert [(standing.state, standing.invitation.id, standing.invitation.epoch) for standing in shown] == [
            (MembershipState.INVITED, offer.id, 4)
        ]
        assert [standing.state for standing in restarted.standings_of(BACH.account_id)] == [MembershipState.ACTIVE]


class TestRetention:
    def test_an_accept_ends_the_invitation_and_keeps_the_row_with_its_epoch_and_no_person(
        self, service, engine, table_id
    ):
        offer = invite(service, table_id, MOZART)

        assert accept(service, table_id, MOZART, offer).refusal is None

        assert tuple(book_row(engine, MOZART)) == (0, None, None, None, None)

    def test_a_refusal_that_ends_the_invitation_keeps_the_caller_and_the_outcome_while_it_is_told(
        self, service, engine, table_id
    ):
        offer = invite(service, table_id, MOZART)

        result = service.accept_invitation(
            MOZART, OPENER.account_id, Acceptance(table_id, offer.id, offer.epoch), frozenset()
        )

        assert result.refusal is MemberRefusal.SPONSOR_AWAY
        row = book_row(engine, MOZART)
        assert (row.inviter_account, row.ended_outcome) == (OPENER.account_id, CallOutcome.OWNER_ABSENT.value)

    def test_a_read_after_the_outcome_was_kept_forgets_the_invitation_and_its_two_people(
        self, service, engine, transactions, table_id
    ):
        invite(service, table_id, MOZART)
        later = TableService(transactions, now=lambda: LATER + ENDED_CALL_KEPT)

        assert later.standings_of(MOZART.account_id) == ()

        assert tuple(book_row(engine, MOZART)) == (0, None, None, None, None)

    def test_a_read_while_the_outcome_is_kept_forgets_nothing(self, service, engine, transactions, table_id):
        invite(service, table_id, MOZART)
        later = TableService(transactions, now=lambda: LATER + timedelta(seconds=1))

        assert later.standings_of(MOZART.account_id) == ()

        assert book_row(engine, MOZART).inviter_account == OPENER.account_id

    def test_a_new_invitation_replaces_the_people_of_an_expired_one(self, service, engine, transactions, table_id):
        invite(service, table_id, MOZART)
        later = TableService(transactions, now=lambda: LATER + ENDED_CALL_KEPT)
        facts = call_facts("account-mozart", "account-new-owner", "account-new-inviter")

        later.invite_agent(TableId(table_id), facts, LASTING)

        assert book_row(engine, MOZART).owner_account == "account-new-owner"

    def test_the_end_of_the_table_removes_every_row_of_it(self, service, engine, table_id):
        invite(service, table_id, MOZART)
        invite(service, table_id, BACH)

        assert service.end_empty_table(TableId(table_id), nullcontext(frozenset()), 60) is True

        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM member_book")).scalar_one() == 0
