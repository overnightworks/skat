from datetime import UTC, datetime

import pytest

from skat.table.records import Actor, CreateTable, Ending, SitDown, StandUp, TableId
from skat.table.transactions import TableVersion
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS

pytestmark = pytest.mark.postgres

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
NOBODY_CONNECTED = frozenset[str]()


def open_table(service, opener, name):
    return TableId(service.create(opener, CreateTable(command_id=f"open-{name}")).id)


def tables_of(transactions, account_id):
    with transactions.begin() as transaction:
        return transaction.tables_of(account_id)


def test_an_accounts_live_tables_come_with_their_versions_in_id_order(service, transactions, stored):
    opened = [open_table(service, ANNA, name) for name in "abcde"]
    ended, left, *kept = opened
    other = open_table(service, BEN, "other")
    service.sit(ANNA, SitDown("sit-other", other.value, 2), NOBODY_CONNECTED)
    service.stand(ANNA, StandUp("stand-left", left.value), NOBODY_CONNECTED)
    with transactions.begin() as transaction:
        transaction.end_table(ended, datetime(2026, 11, 9, 12, tzinfo=UTC), Ending.empty(DEFAULT_EMPTY_TABLE_SECONDS))

    held = tables_of(transactions, ANNA.account_id)

    held_ids = sorted((*kept, other), key=lambda table_id: table_id.value)
    assert held == tuple(TableVersion(table_id, stored(transactions, table_id.value).version) for table_id in held_ids)


def test_an_account_that_holds_no_chair_has_no_tables(service, transactions):
    open_table(service, ANNA, "a")

    assert tables_of(transactions, BEN.account_id) == ()


def test_the_versions_of_named_tables_leave_out_an_ended_one_and_any_that_was_not_named(service, transactions, stored):
    named, ended, _unnamed = (open_table(service, ANNA, name) for name in "abc")
    with transactions.begin() as transaction:
        transaction.end_table(ended, datetime(2026, 11, 9, 12, tzinfo=UTC), Ending.empty(DEFAULT_EMPTY_TABLE_SECONDS))

    with transactions.begin() as transaction:
        versions = transaction.versions_of([named, ended, TableId("0" * 32)])

    assert versions == (TableVersion(named, stored(transactions, named.value).version),)
