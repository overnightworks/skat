from datetime import UTC, datetime

import pytest

from skat.table.records import Actor, CreateTable, SitDown, StandUp, TableId
from skat.table.transactions import HeldTable
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
        transaction.end_table(ended, datetime(2026, 11, 9, 12, tzinfo=UTC), DEFAULT_EMPTY_TABLE_SECONDS)

    held = tables_of(transactions, ANNA.account_id)

    held_ids = sorted((*kept, other), key=lambda table_id: table_id.value)
    assert held == tuple(HeldTable(table_id, stored(transactions, table_id.value).version) for table_id in held_ids)


def test_an_account_that_holds_no_chair_has_no_tables(service, transactions):
    open_table(service, ANNA, "a")

    assert tables_of(transactions, BEN.account_id) == ()
