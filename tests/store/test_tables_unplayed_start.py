import pytest
from sqlalchemy import select, text

from skat.store.schema import tables
from skat.table.records import Actor, CreateTable, SitDown
from skat.table.service import TableService
from tests.web.support.skat import FakeTime, Skat

pytestmark = pytest.mark.postgres

UNPLAYED_DAYS = 90
SEATED = (
    Actor(account_id="account-anna", display_name="Anna"),
    Actor(account_id="account-ben", display_name="Ben"),
    Actor(account_id="account-cleo", display_name="Cleo"),
)


@pytest.fixture
def due_table(transactions, engine):
    """A dealt table of a stopped server whose last deal lies one second more than the days back."""
    service = TableService(transactions)
    table_id = service.create(SEATED[0], CreateTable(command_id="command-open")).id
    for seat, actor in enumerate(SEATED[1:], start=2):
        service.sit(actor, SitDown(f"command-sit-{seat}", table_id, seat), frozenset())
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE tables SET last_played_at = now() - make_interval(days => :days, secs => 1)").bindparams(
                days=UNPLAYED_DAYS
            )
        )
    return table_id


def start_and_stop(transactions, sign_in_settings):
    time = FakeTime()
    server = Skat(
        lambda: sign_in_settings(paused_table_days=UNPLAYED_DAYS),
        store=transactions,
        chair_clock=time.clock,
        chair_scheduler=time,
    )
    with server.client:
        pass


def stored_row(engine, table_id):
    with engine.connect() as connection:
        return tuple(
            connection.execute(
                select(tables.c.version, tables.c.end_reason, tables.c.unplayed_days, tables.c.last_played_at).where(
                    tables.c.id == table_id
                )
            ).one()
        )


def test_a_server_started_after_the_days_ended_the_table_in_the_database_and_a_second_start_changes_nothing(
    due_table, transactions, engine, sign_in_settings
):
    version = stored_row(engine, due_table)[0]

    start_and_stop(transactions, sign_in_settings)
    ended = stored_row(engine, due_table)
    start_and_stop(transactions, sign_in_settings)

    assert ended == (version + 1, "unplayed", UNPLAYED_DAYS, None)
    assert stored_row(engine, due_table) == ended


def test_a_table_with_time_left_is_kept_by_the_start(due_table, transactions, engine, sign_in_settings):
    with engine.begin() as connection:
        connection.execute(text("UPDATE tables SET last_played_at = now() - interval '1 day'"))
    before = stored_row(engine, due_table)

    start_and_stop(transactions, sign_in_settings)

    assert stored_row(engine, due_table) == before
