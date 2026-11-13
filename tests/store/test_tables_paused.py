import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from skat.store.schema import tables
from skat.table.records import Actor, CreateTable, Ending, SitDown, TableId
from skat.table.service import TableService
from skat.table.transactions import PausedFacts

pytestmark = pytest.mark.postgres

OPENER = Actor(account_id="account-anna", display_name="Anna")
VISITOR = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DEALT_AT = datetime(2026, 11, 1, 12, tzinfo=UTC)
LATER = DEALT_AT + timedelta(days=2)
NOBODY_CONNECTED = frozenset[str]()


@pytest.fixture
def service(transactions):
    return TableService(transactions, random_source=random.Random(8), now=lambda: DEALT_AT)  # noqa: S311 - a seeded source makes the deal reproducible


@pytest.fixture
def opened(service):
    return service.create(OPENER, CreateTable(command_id="open")).id


@pytest.fixture
def dealt(service, opened):
    for seat, person in ((2, VISITOR), (3, CLEO)):
        service.sit(person, SitDown(f"sit-{seat}", opened, seat), NOBODY_CONNECTED)
    return opened


def facts_of(transactions, table_id):
    with transactions.begin() as transaction:
        return transaction.paused_facts(TableId(table_id))


def columns_of(engine, table_id):
    with engine.connect() as connection:
        return tuple(
            connection.execute(
                select(tables.c.last_played_at, tables.c.opener_name).where(tables.c.id == table_id)
            ).one()
        )


class TestTheOpenersName:
    def test_the_name_the_opener_had_at_opening_is_stored_with_the_table(self, engine, opened):
        assert columns_of(engine, opened) == (None, "Anna")


class TestTheLastPlayedTime:
    def test_a_table_before_its_first_deal_has_the_openers_name_and_no_time(self, transactions, opened):
        assert facts_of(transactions, opened) == PausedFacts(None, "Anna")

    def test_the_deal_stores_its_time_together_with_the_opener(self, transactions, dealt):
        assert facts_of(transactions, dealt) == PausedFacts(DEALT_AT, "Anna")

    def test_a_save_with_a_time_moves_it_and_a_save_with_none_leaves_it(self, transactions, dealt):
        with transactions.begin() as transaction:
            record = transaction.locked_table(TableId(dealt))
            transaction.save_table(replace(record, version=record.version + 1), played_at=LATER)
        with transactions.begin() as transaction:
            record = transaction.locked_table(TableId(dealt))
            transaction.save_table(replace(record, version=record.version + 1), played_at=None)

        assert facts_of(transactions, dealt).last_played_at == LATER

    def test_a_dealer_saved_with_no_time_is_refused_and_nothing_is_stored(self, engine, transactions, opened):
        with transactions.begin() as transaction:
            record = transaction.locked_table(TableId(opened))
        with pytest.raises(IntegrityError), transactions.begin() as transaction:
            transaction.save_table(replace(record, version=record.version + 1, dealer=1), played_at=None)

        with transactions.begin() as transaction:
            stored = transaction.table(TableId(opened))
        assert (stored.version, stored.dealer, columns_of(engine, opened)[0]) == (1, None, None)


class TestTheEnd:
    def test_clears_both_facts_in_the_row(self, engine, transactions, dealt):
        with transactions.begin() as transaction:
            assert transaction.locked_table(TableId(dealt)) is not None
            transaction.end_table(TableId(dealt), LATER, Ending.empty(60))

        assert columns_of(engine, dealt) == (None, None)
