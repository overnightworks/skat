"""A next-deal pause and an empty table's wait are deadlines stored beside the table, on the database's clock, and the
release before keeps dealing from its own timers and ends from its own, so each deadline's step, under the table's row
lock, acts once beside a deal or an end that other release committed.
"""

import random
from contextlib import nullcontext
from datetime import timedelta

import pytest
from sqlalchemy import func, insert, select, update

from skat.engine.deal import Position, positions_from
from skat.store.schema import next_deals, tables
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.records import Ending, EndReason
from skat.table.rules import NEXT_DEAL_PAUSE_SECONDS, dealt_next, drawn_hand
from skat.table.service import TableService
from tests.support.ended_tables import POSTGRES_EMPTY_SECONDS, lapse_the_empty_wait
from tests.support.seated_tables import ENDED_AT, NOBODY_CONNECTED, SEATED, ended_at, seated_table, undealt_table
from tests.support.stored_game import next_deals as stored_next_deals
from tests.support.table_rows import WorkInAThread, wait_until_a_session_waits_for_a_lock

pytestmark = pytest.mark.postgres

ALL_THREE = frozenset(actor.account_id for actor in SEATED)
# The longest a step of the test may take between the store's clock and the assertion.
STEP_SECONDS = 5
FORGET_AFTER_DAYS = 7


def pass_in(service, transactions, stored, table_id):
    """The three passes the bid route takes, in turn, which end the hand."""
    for position in (Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND):
        record = stored(transactions, table_id.value)
        seat = next(seat for seat, each in positions_from(record.dealer).items() if each is position)
        command = AuctionCommand(
            command_id=f"pass-{position.name}",
            table_id=table_id.value,
            version=record.version,
            action=AuctionAction.PASS,
            value=None,
        )
        assert service.take_auction_step(SEATED[seat - 1], command, NOBODY_CONNECTED).refusal is None


def pause_due_in(engine, table_id, seconds):
    with engine.begin() as connection:
        connection.execute(
            update(next_deals)
            .where(next_deals.c.table_id == table_id.value)
            .values(due_at=func.now() + timedelta(seconds=seconds))
        )


def pause_rows(engine):
    return [table_id for table_id, _ in stored_next_deals(engine)]


def seconds_until_the_pause_is_over(engine, table_id):
    with engine.connect() as connection:
        return connection.execute(
            select(func.extract("epoch", next_deals.c.due_at - func.now())).where(
                next_deals.c.table_id == table_id.value
            )
        ).scalar_one()


def version_of(stored, transactions, table_id):
    return stored(transactions, table_id.value).version


def deals_as_the_release_before_does(transaction, table_id):
    """The release before's deal: under the row lock, a new hand saved, and no pause row dropped, as it knows none."""
    table = transaction.locked_table(table_id)
    transaction.save_table(dealt_next(table, drawn_hand(table, random.Random(3))), played_at=None)  # noqa: S311 - a seeded source makes the deal reproducible


@pytest.fixture
def passed_in_table(service, transactions, stored):
    table_id = seated_table(service, "passed-in")
    pass_in(service, transactions, stored, table_id)
    return table_id


class TestThePause:
    def test_the_hand_ending_commit_stores_the_pause_due_one_pause_from_the_database_clock(
        self, engine, passed_in_table
    ):
        assert pause_rows(engine) == [passed_in_table.value]
        assert seconds_until_the_pause_is_over(engine, passed_in_table) > NEXT_DEAL_PAUSE_SECONDS - STEP_SECONDS
        assert seconds_until_the_pause_is_over(engine, passed_in_table) <= NEXT_DEAL_PAUSE_SECONDS

    def test_a_pause_not_over_changes_nothing_and_stays(self, service, engine, transactions, stored, passed_in_table):
        version = version_of(stored, transactions, passed_in_table)

        assert service.deal_after_pause(passed_in_table, nullcontext(ALL_THREE)) is False

        assert (version_of(stored, transactions, passed_in_table), pause_rows(engine)) == (
            version,
            [passed_in_table.value],
        )

    def test_a_pause_that_is_over_deals_once_and_is_gone(self, service, engine, transactions, stored, passed_in_table):
        version = version_of(stored, transactions, passed_in_table)
        pause_due_in(engine, passed_in_table, -1)

        dealt = service.deal_after_pause(passed_in_table, nullcontext(ALL_THREE))
        again = service.deal_after_pause(passed_in_table, nullcontext(ALL_THREE))

        assert (dealt, again) == (True, False)
        assert version_of(stored, transactions, passed_in_table) == version + 1
        assert pause_rows(engine) == []

    def test_a_pause_that_is_over_while_someone_is_away_is_dropped_and_deals_nothing(
        self, service, engine, transactions, stored, passed_in_table
    ):
        version = version_of(stored, transactions, passed_in_table)
        pause_due_in(engine, passed_in_table, -1)

        assert service.deal_after_pause(passed_in_table, nullcontext(ALL_THREE - {SEATED[1].account_id})) is False

        assert (version_of(stored, transactions, passed_in_table), pause_rows(engine)) == (version, [])

    def test_an_unknown_presence_keeps_the_pause(self, service, engine, passed_in_table):
        pause_due_in(engine, passed_in_table, -1)

        assert service.deal_after_pause(passed_in_table, nullcontext(None)) is False

        assert pause_rows(engine) == [passed_in_table.value]

    def test_a_deal_that_failed_is_stored_as_due_now_and_replaces_the_pause_pending(
        self, service, engine, passed_in_table
    ):
        service.deal_next_soon(passed_in_table)

        assert [passed_in_table] == list(service.due_next_deals())
        assert pause_rows(engine) == [passed_in_table.value]

    def test_a_request_during_a_pending_pause_neither_cuts_nor_stretches_it(self, service, engine, passed_in_table):
        pause_due_in(engine, passed_in_table, 2)

        service.pause_next_deal(passed_in_table)

        assert 0 < seconds_until_the_pause_is_over(engine, passed_in_table) <= 2

    def test_a_table_never_dealt_on_gets_no_pause(self, service, engine):
        table_id = undealt_table(service, "undealt")

        service.pause_next_deal(table_id)

        assert pause_rows(engine) == []


class TestThePauseBesideTheReleaseBefore:
    def test_a_deal_the_release_before_committed_before_the_pause_was_over_leaves_the_sweep_nothing_to_deal(
        self, service, engine, transactions, stored, passed_in_table
    ):
        with transactions.begin() as transaction:
            deals_as_the_release_before_does(transaction, passed_in_table)
        dealt = version_of(stored, transactions, passed_in_table)
        pause_due_in(engine, passed_in_table, -1)

        assert service.deal_after_pause(passed_in_table, nullcontext(ALL_THREE)) is False

        assert (version_of(stored, transactions, passed_in_table), pause_rows(engine)) == (dealt, [])

    def test_a_deal_the_release_before_commits_while_the_sweep_waits_for_the_row_is_the_only_deal(
        self, service, engine, transactions, stored, passed_in_table
    ):
        version = version_of(stored, transactions, passed_in_table)
        pause_due_in(engine, passed_in_table, -1)
        sweep = WorkInAThread(lambda: service.deal_after_pause(passed_in_table, nullcontext(ALL_THREE)))

        with transactions.begin() as old_release:
            deals_as_the_release_before_does(old_release, passed_in_table)
            sweep.start()
            wait_until_a_session_waits_for_a_lock(engine, sweep)
        sweep.join(STEP_SECONDS)

        assert sweep.outcome == [False]
        assert (version_of(stored, transactions, passed_in_table), pause_rows(engine)) == (version + 1, [])

    def test_a_hand_ended_by_the_release_before_has_no_pause_row_and_the_sweep_stays_idle_for_its_timers_deal(
        self, service, engine, transactions, stored, passed_in_table
    ):
        with engine.begin() as connection:
            connection.execute(next_deals.delete())
        version = version_of(stored, transactions, passed_in_table)

        assert (service.due_next_deals(), service.deal_after_pause(passed_in_table, nullcontext(ALL_THREE))) == (
            (),
            False,
        )
        assert service.deal_next(passed_in_table, nullcontext(ALL_THREE)) is True

        assert version_of(stored, transactions, passed_in_table) == version + 1

    def test_the_release_befores_forgetting_of_an_ended_table_holding_a_pause_row_succeeds_by_cascade(
        self, service, engine, transactions
    ):
        table_id = undealt_table(service, "forgotten")
        ended_at(transactions, table_id)
        with engine.begin() as connection:
            connection.execute(
                insert(next_deals).values(table_id=table_id.value, due_at=func.now() + timedelta(seconds=1))
            )

        TableService(transactions, now=lambda: ENDED_AT + timedelta(days=FORGET_AFTER_DAYS)).forget_ended_tables(
            FORGET_AFTER_DAYS
        )

        assert pause_rows(engine) == []


class TestTheEmptyEndBesideTheReleaseBefore:
    def test_an_end_the_release_before_commits_while_the_sweep_waits_for_the_row_is_the_only_end(
        self, service, engine, transactions, stored
    ):
        table_id = undealt_table(service, "empty")
        lapse_the_empty_wait(engine, table_id.value)
        sweep = WorkInAThread(
            lambda: service.end_empty_table(table_id, nullcontext(NOBODY_CONNECTED), POSTGRES_EMPTY_SECONDS)
        )

        with transactions.begin() as old_release:
            old_release.locked_table(table_id)
            sweep.start()
            wait_until_a_session_waits_for_a_lock(engine, sweep)
            old_release.end_table(table_id, ENDED_AT, Ending.empty(POSTGRES_EMPTY_SECONDS))
        sweep.join(STEP_SECONDS)

        assert sweep.outcome == [False]
        with engine.connect() as connection:
            assert connection.execute(
                select(tables.c.ended_at, tables.c.end_reason).where(tables.c.id == table_id.value)
            ).one() == (ENDED_AT, EndReason.EMPTY)
