from dataclasses import replace

import pytest
from sqlalchemy import text

from skat.engine.bock import BockOptions, BockOverlap, BockRounds, BockTrigger
from skat.engine.deal import Position
from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.bock import BockView
from skat.table.playing import GiveUpCommand
from skat.table.records import Actor, CreateTable, TableId, TableOptions
from skat.table.service import TableService
from tests.support.stored_game import seated_game

pytestmark = pytest.mark.postgres

OPENER = Actor(account_id="account-opener", display_name="Anna")


@pytest.fixture
def engine(database_url):
    engine = create_store_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def service(engine):
    return TableService(PostgresTableTransactions(engine))


BOCK_OPTIONS = TableOptions(bock=BockOptions(frozenset({BockTrigger.PASSED_IN, BockTrigger.RE}), BockOverlap.MULTIPLY))


def hold_pending_bock_games(transactions, table_id, *rounds):
    with transactions.begin() as transaction:
        transaction.save_table(replace(transaction.locked_table(TableId(table_id)), bock=BockRounds(rounds)))


def test_a_table_reads_back_its_bock_options_and_its_pending_games_after_a_restart(service, transactions, database_url):
    created = service.create(OPENER, CreateTable(command_id="command-1", options=BOCK_OPTIONS))
    hold_pending_bock_games(transactions, created.id, 2, 3)
    restarted_engine = create_store_engine(database_url)
    try:
        restarted = TableService(PostgresTableTransactions(restarted_engine))

        view = restarted.view(OPENER, created.id, frozenset())
    finally:
        restarted_engine.dispose()

    assert view.options.bock == BOCK_OPTIONS.bock
    assert view.bock == BockView(games_left=3, factor=4)


def test_a_table_opened_without_bock_reads_back_no_bock_and_no_pending_game(service, transactions, stored):
    table_id = service.create(OPENER, CreateTable(command_id="command-1")).id

    record = stored(transactions, table_id)

    assert (record.options.bock, record.bock) == (None, BockRounds(()))


def test_a_bock_game_stores_its_multiplied_score_and_its_factor_and_the_games_left_count_down(
    service, transactions, stored, engine
):
    game = seated_game(service, transactions, stored, BOCK_OPTIONS)
    hold_pending_bock_games(transactions, game.table_id, 3)
    command = GiveUpCommand(command_id="give-up", table_id=game.table_id, version=game.record.version)

    result = game.service.give_up(game.actors[Position.MIDDLEHAND], command, frozenset(), lambda _accounts: None)

    assert result.refusal is None
    with engine.connect() as connection:
        settled_value, score, factor = connection.execute(
            text("SELECT settled_value, score, bock_factor FROM game_list")
        ).one()
    # A lost game scores minus twice its value, and the one pending round doubles that.
    assert (score, factor) == (-2 * settled_value * 2, 2)
    assert (game.record.game_list[0].bock_factor, game.record.bock) == (2, BockRounds((2,)))
