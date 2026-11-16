from datetime import timedelta

import pytest
from sqlalchemy import update

from skat.store.schema import tables
from skat.table.records import CloseTable, CreateTable, Ending, EndReason
from skat.table.service import TableService
from tests.support.seated_tables import ENDED_AT, OPENER, ended_at, listed_game, undealt_table
from tests.support.table_rows import WorkInAThread, rows_of, wait_until_a_session_waits_for_a_lock

pytestmark = pytest.mark.postgres

ENDED_TABLE_DAYS = 7
FORGOTTEN_AT = ENDED_AT + timedelta(days=ENDED_TABLE_DAYS)


def forgetting_service(transactions, now=FORGOTTEN_AT):
    return TableService(transactions, now=lambda: now)


def closed_with_games(service, transactions, stored, engine, name):
    table_id = listed_game(service, transactions, stored, name)
    service.close(OPENER, CloseTable(f"close-{name}", table_id.value))
    with engine.begin() as connection:
        connection.execute(update(tables).where(tables.c.id == table_id.value).values(ended_at=ENDED_AT))
    return table_id


def test_forgetting_deletes_an_ended_table_with_no_game_with_its_receipts_once_the_days_are_up(
    service, transactions, stored, engine
):
    table_id = undealt_table(service, "one")
    ended_at(transactions, table_id)
    assert rows_of(engine, table_id.value)["receipts"]

    forgetting_service(transactions).forget_ended_tables(ENDED_TABLE_DAYS)

    assert {name for name, rows in rows_of(engine, table_id.value).items() if rows} == set()
    assert stored(transactions, table_id.value) is None


def test_forgetting_keeps_a_live_table_and_an_ended_table_within_its_days_and_deletes_a_due_one(
    service, transactions, engine
):
    live = undealt_table(service, "live")
    recent = undealt_table(service, "recent")
    due = undealt_table(service, "due")
    ended_at(transactions, recent)
    ended_at(transactions, due)
    with engine.begin() as connection:
        connection.execute(
            update(tables).where(tables.c.id == recent.value).values(ended_at=FORGOTTEN_AT - timedelta(seconds=1))
        )
    live_before = rows_of(engine, live.value)
    recent_before = rows_of(engine, recent.value)

    forgetting_service(transactions).forget_ended_tables(ENDED_TABLE_DAYS)

    assert rows_of(engine, live.value) == live_before
    assert rows_of(engine, recent.value) == recent_before
    assert not any(rows_of(engine, due.value).values())


def test_forgetting_keeps_an_ended_table_with_games_and_clears_only_its_closers_name(
    service, transactions, stored, engine
):
    table_id = closed_with_games(service, transactions, stored, engine, "one")
    before = rows_of(engine, table_id.value)
    version = stored(transactions, table_id.value).version

    forgetting_service(transactions).forget_ended_tables(ENDED_TABLE_DAYS)

    after = rows_of(engine, table_id.value)
    assert {name for name, rows in after.items() if rows} == {"tables", "series", "receipts", "game_list"}
    assert after["game_list"] == before["game_list"]
    assert after["receipts"] == before["receipts"]
    ended = stored(transactions, table_id.value)
    assert (ended.version, ended.ending) == (version, Ending(EndReason.CLOSED))


def test_forgetting_keeps_the_closers_name_of_a_table_with_games_until_the_days_are_up(
    service, transactions, stored, engine
):
    table_id = closed_with_games(service, transactions, stored, engine, "one")
    before = stored(transactions, table_id.value)

    forgetting_service(transactions, FORGOTTEN_AT - timedelta(seconds=1)).forget_ended_tables(ENDED_TABLE_DAYS)

    assert stored(transactions, table_id.value) == before


def test_a_create_retry_that_reads_its_receipt_as_the_forgetting_deletes_the_table_makes_a_new_table(
    service, transactions, engine
):
    forgotten = undealt_table(service, "one")
    ended_at(transactions, forgotten)

    with transactions.begin() as forgetting:
        forgetting.forget_ended_before(FORGOTTEN_AT)
        retry = WorkInAThread(lambda: service.create(OPENER, CreateTable(command_id="open-one")))
        retry.start()
        wait_until_a_session_waits_for_a_lock(engine, retry)

    retry.join()
    assert retry.outcome[0].id != forgotten.value
    assert not any(rows_of(engine, forgotten.value).values())
