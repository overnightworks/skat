import threading
from contextlib import nullcontext

import pytest

from skat.engine.deal import Position, positions_from
from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.records import Actor, CreateTable, Series, SitDown, StandUp, TableId
from skat.table.service import TableService
from tests.support.faulty_tables import BothReadBeforeEitherWrites

pytestmark = pytest.mark.postgres

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")
THIRD_PLAYER = Actor(account_id="account-third", display_name="Cleo")
PEOPLE = {1: OPENER, 2: VISITOR, 3: THIRD_PLAYER}
ALL_THREE = frozenset(person.account_id for person in PEOPLE.values())


def read(transactions, table_id):
    with transactions.begin() as transaction:
        return transaction.table(TableId(table_id))


def series_of(transactions, table_id):
    return read(transactions, table_id).series


def pass_the_hand_in(service, transactions, table_id):
    record = read(transactions, table_id)
    by_position = {position: PEOPLE[seat] for seat, position in positions_from(record.dealer).items()}
    for step, position in enumerate((Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND)):
        command = AuctionCommand(
            f"pass-{record.version}-{step}", table_id, record.version + step, AuctionAction.PASS, None
        )
        assert service.take_auction_step(by_position[position], command, frozenset()).refusal is None


@pytest.fixture
def table_id(service):
    """A series of three games, its first game dealt by the last sit."""
    table_id = service.create(OPENER, CreateTable(command_id="command-open", series_length=3)).id
    service.sit(VISITOR, SitDown("command-visitor", table_id, 2), frozenset())
    service.sit(THIRD_PLAYER, SitDown("command-third", table_id, 3), frozenset())
    return table_id


def test_a_restart_between_deals_keeps_the_count_and_after_the_last_game_deals_no_more(
    service, transactions, table_id, database_url
):
    assert series_of(transactions, table_id) == Series(3, 1)
    for expected_deals in (2, 3):
        pass_the_hand_in(service, transactions, table_id)
        restarted_engine = create_store_engine(database_url)
        restarted = TableService(PostgresTableTransactions(restarted_engine))
        assert restarted.deal_next(TableId(table_id), nullcontext(ALL_THREE)) is True
        assert series_of(PostgresTableTransactions(restarted_engine), table_id) == Series(3, expected_deals)
        restarted_engine.dispose()

    pass_the_hand_in(service, transactions, table_id)
    restarted_engine = create_store_engine(database_url)
    try:
        restarted = TableService(PostgresTableTransactions(restarted_engine))
        assert restarted.deal_next(TableId(table_id), nullcontext(ALL_THREE)) is False
        assert series_of(PostgresTableTransactions(restarted_engine), table_id) == Series(3, 3)
    finally:
        restarted_engine.dispose()


def test_a_stand_and_a_sit_mid_series_leave_the_count_standing(service, transactions, table_id):
    pass_the_hand_in(service, transactions, table_id)
    service.stand(THIRD_PLAYER, StandUp("command-stand", table_id), frozenset())
    assert series_of(transactions, table_id) == Series(3, 1)

    service.sit(THIRD_PLAYER, SitDown("command-sit-again", table_id, 3), frozenset())

    assert series_of(transactions, table_id) == Series(3, 2)


def test_two_checks_at_once_deal_one_hand_and_count_one_deal(service, transactions, table_id):
    pass_the_hand_in(service, transactions, table_id)
    racing = TableService(BothReadBeforeEitherWrites(transactions, 2))
    answers = []

    def check():
        answers.append(racing.deal_next(TableId(table_id), nullcontext(ALL_THREE)))

    threads = [threading.Thread(target=check), threading.Thread(target=check)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(answers) == [False, True]
    assert series_of(transactions, table_id) == Series(3, 2)


def test_a_replay_of_the_sit_that_dealt_counts_no_second_deal(service, transactions, table_id):
    service.sit(THIRD_PLAYER, SitDown("command-third", table_id, 3), frozenset())

    assert series_of(transactions, table_id) == Series(3, 1)
