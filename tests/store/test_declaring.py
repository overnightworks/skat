import random
import threading
from dataclasses import replace

import pytest
from sqlalchemy import func, select, table, text

from skat.engine.deal import Position, positions_from
from skat.engine.declaration import Announcement, Declare, DeclarationRefusal, PutBack, TakeSkat
from skat.engine.games import GameKind
from skat.store.migrate import create_store_engine
from skat.store.schema import StepLogRewrittenError
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.declaring import DeclaringCommand
from skat.table.records import Actor, CreateTable, Refusal, SitDown, TableId
from skat.table.service import TableService
from tests.support.faulty_tables import BothReadBeforeEitherWrites, FaultyTableTransactions

pytestmark = pytest.mark.postgres

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
NOBODY_CONNECTED: frozenset[str] = frozenset()
FIRST_STEP, SECOND_STEP, THIRD_STEP = "command-a", "command-b", "command-c"
HERZ_HAND = Declare(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.NONE)
HERZ_AFTER_PICK_UP = Declare(GameKind.HERZ, hand=False, ouvert=False, announcement=Announcement.NONE)


@pytest.fixture
def engine(database_url):
    engine = create_store_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def transactions(engine):
    return PostgresTableTransactions(engine)


@pytest.fixture
def service(transactions):
    return TableService(transactions, random_source=random.Random(8))  # noqa: S311 - a seeded source makes the deal reproducible


def stored(transactions, table_id):
    with transactions.begin() as transaction:
        return transaction.table(TableId(table_id))


def count_steps(engine):
    with engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(table("declaring_steps"))).scalar_one()


class Hand:
    """A table whose middlehand won the auction at 20."""

    def __init__(self, service, transactions, table_id):
        self.service = service
        self.transactions = transactions
        self.table_id = table_id
        record = stored(transactions, table_id)
        by_seat = {1: ANNA, 2: BEN, 3: CLEO}
        self.actors = {position: by_seat[seat] for seat, position in positions_from(record.dealer).items()}
        self._auction(Position.MIDDLEHAND, AuctionAction.BID, 20, "bid")
        self._auction(Position.FOREHAND, AuctionAction.PASS, None, "forehand-passes")
        self._auction(Position.REARHAND, AuctionAction.PASS, None, "rearhand-passes")

    def _auction(self, position, action, value, command_id):
        version = stored(self.transactions, self.table_id).version
        command = AuctionCommand(command_id=command_id, table_id=self.table_id, version=version, action=action, value=value)
        self.service.take_auction_step(self.actors[position], command, NOBODY_CONNECTED)

    def twelve_cards(self):
        record = stored(self.transactions, self.table_id)
        return (*record.hand.hands[Position.MIDDLEHAND], *record.hand.skat)

    def send(self, step, *, command_id, version=None, service=None):
        record = stored(self.transactions, self.table_id)
        command = DeclaringCommand(
            command_id=command_id,
            table_id=self.table_id,
            version=record.version if version is None else version,
            step=step,
        )
        return (service or self.service).take_declaring_step(self.actors[Position.MIDDLEHAND], command, NOBODY_CONNECTED)

    def steps(self):
        return stored(self.transactions, self.table_id).progress.declaring


@pytest.fixture
def hand(service, transactions):
    table_id = service.create(ANNA, CreateTable(command_id="command-open")).id
    service.sit(BEN, SitDown("command-ben", table_id, 2), NOBODY_CONNECTED)
    service.sit(CLEO, SitDown("command-cleo", table_id, 3), NOBODY_CONNECTED)
    return Hand(service, transactions, table_id)


def test_the_steps_read_back_in_the_order_they_were_taken(hand):
    twelve = hand.twelve_cards()

    hand.send(TakeSkat(), command_id=FIRST_STEP)
    hand.send(PutBack((twelve[0], twelve[11])), command_id=SECOND_STEP)
    hand.send(HERZ_AFTER_PICK_UP, command_id=THIRD_STEP)

    assert hand.steps() == (TakeSkat(), PutBack((twelve[0], twelve[11])), HERZ_AFTER_PICK_UP)


def test_every_field_of_a_declaration_reads_back(hand):
    ouvert_suit = Declare(GameKind.GRAND, hand=True, ouvert=True, announcement=Announcement.SCHWARZ)

    hand.send(ouvert_suit, command_id=FIRST_STEP)

    assert hand.steps() == (ouvert_suit,)


def test_taking_the_skat_and_putting_back_keep_the_dealt_hand_as_dealt(hand, engine, transactions):
    before = stored(transactions, hand.table_id).hand
    twelve = hand.twelve_cards()

    hand.send(TakeSkat(), command_id=FIRST_STEP)
    hand.send(PutBack((twelve[10], twelve[11])), command_id=SECOND_STEP)

    assert stored(transactions, hand.table_id).hand == before
    with engine.connect() as connection:
        skat_rows = connection.execute(
            text("SELECT count(*) FROM hand_cards WHERE table_id = :id AND holder = 'skat'"), {"id": hand.table_id}
        ).scalar_one()
    assert skat_rows == 2


def test_a_retry_stores_no_second_step_and_no_second_version(hand, engine, transactions):
    version = stored(transactions, hand.table_id).version
    first = hand.send(TakeSkat(), command_id=FIRST_STEP, version=version)

    again = hand.send(TakeSkat(), command_id=FIRST_STEP, version=version)

    assert again == first
    assert count_steps(engine) == 1
    assert stored(transactions, hand.table_id).version == version + 1


def test_a_refused_step_keeps_its_token_in_the_receipt_for_a_retry(hand, engine):
    first = hand.send(HERZ_AFTER_PICK_UP, command_id=FIRST_STEP)

    again = hand.send(HERZ_AFTER_PICK_UP, command_id=FIRST_STEP)

    assert first.refusal is DeclarationRefusal.OUT_OF_ORDER
    assert again.refusal is first.refusal
    with engine.connect() as connection:
        token = connection.execute(text("SELECT refusal FROM receipts WHERE command_id = 'command-a'")).scalar_one()
    assert token == first.refusal.value


def test_two_takes_at_once_store_exactly_one_step_and_name_the_loser_stale(hand, engine, transactions):
    version = stored(transactions, hand.table_id).version
    racing = TableService(BothReadBeforeEitherWrites(transactions, 2))
    results: list[object] = []

    def request(command_id):
        results.append(hand.send(TakeSkat(), command_id=command_id, version=version, service=racing))

    threads = [threading.Thread(target=request, args=(name,)) for name in (FIRST_STEP, SECOND_STEP)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert count_steps(engine) == 1
    assert sorted(str(result.refusal) for result in results) == sorted([str(None), str(Refusal.STALE_VERSION)])


def test_a_restart_reads_the_identical_steps_and_the_next_step_continues(hand, database_url):
    twelve = hand.twelve_cards()
    hand.send(TakeSkat(), command_id=FIRST_STEP)

    restarted_engine = create_store_engine(database_url)
    try:
        restarted = PostgresTableTransactions(restarted_engine)
        assert stored(restarted, hand.table_id).progress.declaring == hand.steps()
        result = hand.send(PutBack((twelve[0], twelve[1])), command_id=SECOND_STEP, service=TableService(restarted))
    finally:
        restarted_engine.dispose()

    assert result.refusal is None
    assert hand.steps() == (TakeSkat(), PutBack((twelve[0], twelve[1])))


def test_a_failure_inside_the_command_stores_no_step_no_version_and_no_receipt(hand, engine, transactions):
    before = stored(transactions, hand.table_id)
    failing = TableService(FaultyTableTransactions(transactions, save_failure=ConnectionError("lost")))

    with pytest.raises(ConnectionError):
        hand.send(TakeSkat(), command_id=FIRST_STEP, service=failing)

    assert stored(transactions, hand.table_id) == before
    assert count_steps(engine) == 0
    with engine.connect() as connection:
        receipts = connection.execute(text("SELECT count(*) FROM receipts WHERE command_id = 'command-a'")).scalar_one()
    assert receipts == 0


def _rewrite(transactions, table_id, steps):
    before = stored(transactions, table_id)
    rewritten = replace(
        before, version=before.version + 1, progress=replace(before.progress, declaring=steps)
    )
    with transactions.begin() as transaction:
        transaction.save_table(rewritten)


def test_steps_that_rewrite_a_stored_step_raise_and_change_nothing(hand, transactions):
    hand.send(TakeSkat(), command_id=FIRST_STEP)
    before = stored(transactions, hand.table_id)
    rewritten_steps = (HERZ_HAND,)

    with pytest.raises(StepLogRewrittenError):
        _rewrite(transactions, hand.table_id, rewritten_steps)

    assert stored(transactions, hand.table_id) == before


def test_steps_shorter_than_the_stored_ones_raise_and_change_nothing(hand, transactions):
    hand.send(TakeSkat(), command_id=FIRST_STEP)
    before = stored(transactions, hand.table_id)
    no_steps: tuple[Declare, ...] = ()

    with pytest.raises(StepLogRewrittenError):
        _rewrite(transactions, hand.table_id, no_steps)

    assert stored(transactions, hand.table_id) == before


def test_a_stored_log_the_engine_refuses_raises_at_the_next_command(hand, engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO declaring_steps VALUES "
                "(:table_id, 1, 'put-back', 'hearts', 'ace', 'spades', 'ace', NULL, NULL, NULL, NULL)"
            ),
            {"table_id": hand.table_id},
        )

    with pytest.raises(ValueError, match="impossible declaring log"):
        hand.send(TakeSkat(), command_id=FIRST_STEP)
