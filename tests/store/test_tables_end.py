import threading
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from skat.store.schema import tables
from skat.table.records import Actor, CreateTable, EndedTable, EndReason, SitDown, TableId, TableRecord
from skat.table.rules import CREATE_TABLE_COMMAND
from skat.table.service import TableService
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.support.faulty_tables import FaultyTableTransactions
from tests.support.played_game import after_the_first_game, before_the_last_card
from tests.support.table_rows import rows_of, wait_until_a_session_waits_for_a_lock

pytestmark = pytest.mark.postgres

NOBODY_CONNECTED = frozenset[str]()
HAND_TABLES = ("hand_cards", "auction_actions", "declaring_steps", "played_cards")
OPENER = Actor(account_id="account-anna", display_name="Anna")
SEATED = (
    OPENER,
    Actor(account_id="account-ben", display_name="Ben"),
    Actor(account_id="account-cleo", display_name="Cleo"),
)


def seated_table(service, name, seats=3):
    """A table with the opener and the next `seats - 1` people seated; the third sitting deals the first hand."""
    table_id = service.create(OPENER, CreateTable(command_id=f"open-{name}")).id
    for seat, actor in enumerate(SEATED[1:seats], start=2):
        service.sit(actor, SitDown(f"sit-{name}-{seat}", table_id, seat), NOBODY_CONNECTED)
    return TableId(table_id)


def undealt_table(service, name):
    return seated_table(service, name, seats=2)


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


def end(service, table_id):
    return service.end_empty_table(table_id, nullcontext(NOBODY_CONNECTED), DEFAULT_EMPTY_TABLE_SECONDS)


def end_at_the_store(transactions, table_id):
    with transactions.begin() as transaction:
        assert transaction.locked_table(table_id) is not None
        transaction.end_table(table_id, datetime(2026, 11, 9, 12, 0, tzinfo=UTC), DEFAULT_EMPTY_TABLE_SECONDS)


def test_the_end_step_deletes_the_chairs_hand_and_steps_of_a_running_hand_and_keeps_the_row(
    service, transactions, stored, engine
):
    table_id = played_hand(service, transactions, stored, "one")
    before = rows_of(engine, table_id.value)
    assert all(before[name] for name in ("chairs", *HAND_TABLES))

    end_at_the_store(transactions, table_id)

    after = rows_of(engine, table_id.value)
    kept = {name for name, rows in after.items() if rows}
    assert kept == {"tables", "receipts"}
    assert len(after["tables"]) == 1


@pytest.mark.parametrize("make", [played_hand, listed_game], ids=["running-hand", "game-list"])
def test_a_dealt_table_nobody_is_connected_to_is_kept_with_every_row(make, service, transactions, stored, engine):
    table_id = make(service, transactions, stored, "one")
    before = rows_of(engine, table_id.value)
    version = stored(transactions, table_id.value).version

    assert end(service, table_id) is False

    assert rows_of(engine, table_id.value) == before
    assert stored(transactions, table_id.value).version == version


def test_an_end_whose_store_fails_after_it_writes_leaves_the_table_live_with_all_its_rows(
    service, transactions, stored, engine
):
    table_id = undealt_table(service, "one")
    before = rows_of(engine, table_id.value)
    failing = TableService(FaultyTableTransactions(transactions, end_failure=ConnectionError("lost")))
    nobody_connected = nullcontext(NOBODY_CONNECTED)

    with pytest.raises(ConnectionError):
        failing.end_empty_table(table_id, nobody_connected, DEFAULT_EMPTY_TABLE_SECONDS)

    assert rows_of(engine, table_id.value) == before
    assert isinstance(stored(transactions, table_id.value), TableRecord)


def test_the_end_step_deletes_the_game_list(service, transactions, stored, engine):
    table_id = listed_game(service, transactions, stored, "one")
    assert rows_of(engine, table_id.value)["game_list"]

    end_at_the_store(transactions, table_id)

    assert rows_of(engine, table_id.value)["game_list"] == []


def test_ending_a_table_keeps_its_create_receipt_and_deletes_every_other_receipt_of_it(
    service, transactions, stored, engine
):
    table_id = undealt_table(service, "one")
    assert len(rows_of(engine, table_id.value)["receipts"]) == 2

    end(service, table_id)

    assert [row[:3] for row in rows_of(engine, table_id.value)["receipts"]] == [
        (OPENER.account_id, "open-one", CREATE_TABLE_COMMAND)
    ]


def test_ending_one_table_changes_no_row_of_another_table_of_the_same_opener_or_of_its_receipts(
    service, transactions, stored, engine
):
    ended = undealt_table(service, "one")
    kept = played_hand(service, transactions, stored, "two")
    other = listed_game(service, transactions, stored, "three")
    before = (rows_of(engine, kept.value), rows_of(engine, other.value))

    assert end(service, ended) is True

    assert (rows_of(engine, kept.value), rows_of(engine, other.value)) == before


def test_the_end_stores_the_time_the_reason_and_the_wait_and_bumps_the_version_once(transactions, stored, engine):
    at = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    service = TableService(transactions, now=lambda: at)
    table_id = undealt_table(service, "one")
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


def test_a_read_that_meets_an_end_in_flight_waits_for_its_commit_and_sees_the_ended_table(
    service, transactions, engine
):
    table_id = undealt_table(service, "one")

    with transactions.begin() as ending:
        ending.end_table(table_id, datetime(2026, 11, 9, 12, 0, tzinfo=UTC), DEFAULT_EMPTY_TABLE_SECONDS)
        views = []
        reading = threading.Thread(target=lambda: views.append(service.view(OPENER, table_id.value, NOBODY_CONNECTED)))
        reading.start()
        wait_until_a_session_waits_for_a_lock(engine)

    reading.join()
    assert views[0].ended.reason == EndReason.EMPTY


def test_an_ended_table_reads_as_a_tombstone_and_is_no_live_table_and_no_chair_is_occupied(
    service, transactions, stored
):
    ended = undealt_table(service, "one")
    live = seated_table(service, "two")

    end(service, ended)

    with transactions.begin() as transaction:
        assert transaction.locked_table(ended) is None
        assert isinstance(transaction.locked_table(live), TableRecord)
        assert {chair.table_id for chair in transaction.occupied_chairs()} == {live}
    assert service.live_table_ids() == (live,)
    assert isinstance(stored(transactions, ended.value), EndedTable)


def test_a_create_retry_under_an_ended_tables_command_id_returns_it_and_makes_no_table(service, transactions, engine):
    ended = undealt_table(service, "one")
    end(service, ended)

    again = service.create(OPENER, CreateTable(command_id="open-one"))

    assert again.id == ended.value
    assert again.ended.reason == EndReason.EMPTY
    with engine.connect() as connection:
        assert connection.execute(select(tables.c.id)).all() == [(ended.value,)]


def test_an_ended_tables_id_is_never_issued_again(service, transactions):
    ended = undealt_table(service, "one")
    end(service, ended)
    reusing = TableService(transactions, new_table_id=lambda: ended)
    command = CreateTable(command_id="open-new")

    with pytest.raises(IntegrityError):
        reusing.create(OPENER, command)


def test_the_end_enters_the_presence_once_the_row_is_locked_and_leaves_it_after_the_commit(service, engine):
    table_id = undealt_table(service, "one")
    seen = {}
    lock_attempt = select(tables.c.id).where(tables.c.id == table_id.value).with_for_update(nowait=True)

    @contextmanager
    def presence():
        with engine.connect() as other, pytest.raises(OperationalError):
            other.execute(lock_attempt)
        yield NOBODY_CONNECTED
        with engine.connect() as other:
            ended_at = select(tables.c.ended_at).where(tables.c.id == table_id.value)
            seen["ended_at"] = other.execute(ended_at).scalar_one()

    assert service.end_empty_table(table_id, presence(), DEFAULT_EMPTY_TABLE_SECONDS) is True

    assert seen["ended_at"] is not None
