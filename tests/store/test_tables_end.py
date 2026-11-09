from contextlib import nullcontext
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from skat.store.schema import metadata, tables
from skat.table.records import Actor, CreateTable, EndedTable, EndReason, SitDown, TableId, TableRecord
from skat.table.service import TableService
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.support.played_game import after_the_first_game, before_the_last_card

pytestmark = pytest.mark.postgres

NOBODY_CONNECTED = frozenset[str]()
HAND_TABLES = ("hand_cards", "auction_actions", "declaring_steps", "played_cards")
OPENER = Actor(account_id="account-anna", display_name="Anna")
SEATED = (
    OPENER,
    Actor(account_id="account-ben", display_name="Ben"),
    Actor(account_id="account-cleo", display_name="Cleo"),
)


def seated_table(service, name):
    table_id = service.create(OPENER, CreateTable(command_id=f"open-{name}")).id
    for seat, actor in enumerate(SEATED[1:], start=2):
        service.sit(actor, SitDown(f"sit-{name}-{seat}", table_id, seat), NOBODY_CONNECTED)
    return TableId(table_id)


def save(transactions, record):
    with transactions.begin() as transaction:
        transaction.save_table(record)


def played_hand(service, transactions, stored, name):
    """A seated table whose middlehand declared a Herz Hand game, with every card played but the last."""
    table_id = seated_table(service, name)
    running, _ = before_the_last_card(stored(transactions, table_id.value))
    save(transactions, running)
    return table_id


def listed_game(service, transactions, stored, name):
    table_id = seated_table(service, name)
    save(transactions, after_the_first_game(stored(transactions, table_id.value)))
    return table_id


def rows_of(engine, table_id):
    """Every row of the store that belongs to the table, in every store table."""
    with engine.connect() as connection:
        return {
            each.name: connection.execute(
                select(each)
                .where((each.c.id if each is tables else each.c.table_id) == table_id.value)
                .order_by(*each.primary_key.columns)
            ).all()
            for each in metadata.sorted_tables
        }


def end(service, table_id):
    return service.end_empty_table(table_id, nullcontext(NOBODY_CONNECTED), DEFAULT_EMPTY_TABLE_SECONDS)


def test_ending_a_table_with_a_running_hand_deletes_its_chairs_hand_and_steps_and_keeps_its_row(
    service, transactions, stored, engine
):
    table_id = played_hand(service, transactions, stored, "one")
    before = rows_of(engine, table_id)
    assert all(before[name] for name in ("chairs", *HAND_TABLES))

    assert end(service, table_id) is True

    after = rows_of(engine, table_id)
    assert {name for name, rows in after.items() if rows} == {"tables", "receipts"}
    assert len(after["tables"]) == 1


def test_ending_a_table_deletes_its_game_list(service, transactions, stored, engine):
    table_id = listed_game(service, transactions, stored, "one")
    assert rows_of(engine, table_id)["game_list"]

    end(service, table_id)

    assert rows_of(engine, table_id)["game_list"] == []


def test_ending_a_table_keeps_its_create_receipt_and_deletes_every_other_receipt_of_it(
    service, transactions, stored, engine
):
    table_id = played_hand(service, transactions, stored, "one")
    assert len(rows_of(engine, table_id)["receipts"]) == len(SEATED)

    end(service, table_id)

    assert [(row.account_id, row.command_id, row.command) for row in rows_of(engine, table_id)["receipts"]] == [
        (OPENER.account_id, "open-one", "create-table")
    ]


def test_ending_one_table_changes_no_row_of_another_table_of_the_same_opener_or_of_its_receipts(
    service, transactions, stored, engine
):
    ended = played_hand(service, transactions, stored, "one")
    kept = played_hand(service, transactions, stored, "two")
    other = listed_game(service, transactions, stored, "three")
    before = (rows_of(engine, kept), rows_of(engine, other))

    end(service, ended)

    assert (rows_of(engine, kept), rows_of(engine, other)) == before


def test_the_end_stores_the_time_the_reason_and_the_wait_and_bumps_the_version_once(transactions, stored, engine):
    at = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    service = TableService(transactions, now=lambda: at)
    table_id = seated_table(service, "one")
    version = stored(transactions, table_id.value).version

    service.end_empty_table(table_id, nullcontext(NOBODY_CONNECTED), 42)

    with engine.connect() as connection:
        row = connection.execute(
            select(tables.c.ended_at, tables.c.end_reason, tables.c.empty_seconds, tables.c.dealer).where(
                tables.c.id == table_id.value
            )
        ).one()
    assert tuple(row) == (at, EndReason.EMPTY.value, 42, None)
    assert stored(transactions, table_id.value) == EndedTable(table_id, version + 1, EndReason.EMPTY, 42)


def test_an_ended_table_reads_as_a_tombstone_and_is_no_live_table_and_no_chair_is_occupied(
    service, transactions, stored
):
    ended = seated_table(service, "one")
    live = seated_table(service, "two")

    end(service, ended)

    with transactions.begin() as transaction:
        assert transaction.locked_table(ended) is None
        assert isinstance(transaction.locked_table(live), TableRecord)
        assert {chair.table_id for chair in transaction.occupied_chairs()} == {live}
    assert service.live_table_ids() == (live,)
    assert isinstance(stored(transactions, ended.value), EndedTable)


def test_a_create_retry_under_an_ended_tables_command_id_returns_it_and_makes_no_table(service, transactions, engine):
    ended = seated_table(service, "one")
    end(service, ended)

    again = service.create(OPENER, CreateTable(command_id="open-one"))

    assert (again.id, again.ended.reason) == (ended.value, EndReason.EMPTY)
    with engine.connect() as connection:
        assert connection.execute(select(tables.c.id)).all() == [(ended.value,)]


def test_an_ended_tables_id_is_never_issued_again(service, transactions):
    ended = seated_table(service, "one")
    end(service, ended)
    reusing = TableService(transactions, new_table_id=lambda: ended)

    with pytest.raises(IntegrityError):
        reusing.create(OPENER, CreateTable(command_id="open-new"))
