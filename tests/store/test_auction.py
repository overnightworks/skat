import threading
from dataclasses import replace

import pytest
from sqlalchemy import func, select, table, text

from skat.engine.bidding import Bid, Hold, Pass, PassedIn
from skat.engine.deal import Position, next_dealer, positions_from
from skat.store.migrate import create_store_engine
from skat.store.schema import StepLogRewrittenError
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.hand_state import auction_of
from skat.table.records import Actor, CreateTable, HandProgress, Refusal, SitDown, StandUp
from skat.table.service import TableService
from tests.support.faulty_tables import BothReadBeforeEitherWrites, FaultyTableTransactions

pytestmark = pytest.mark.postgres

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
NOBODY_CONNECTED: frozenset[str] = frozenset()
DORA = Actor(account_id="account-dora", display_name="Dora")
FIRST_STEP, SECOND_STEP, THIRD_STEP = "command-a", "command-b", "command-c"
CARDS_IN_A_HAND = 32


def count_rows(engine, name):
    with engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(table(name))).scalar_one()


def count_steps(engine):
    return count_rows(engine, "auction_actions")


def count_cards(engine):
    return count_rows(engine, "hand_cards")


class Hand:
    """A table whose third sit has dealt, with its seated accounts by position."""

    def __init__(self, service, transactions, stored, table_id):
        self.service = service
        self.transactions = transactions
        self.stored = stored
        self.table_id = table_id
        record = self.stored(transactions, table_id)
        by_seat = {1: ANNA, 2: BEN, 3: CLEO}
        self.actors = {position: by_seat[seat] for seat, position in positions_from(record.dealer).items()}

    def send(self, position, action, value=None, *, command_id, version=None, service=None):
        record = self.stored(self.transactions, self.table_id)
        command = AuctionCommand(
            command_id=command_id,
            table_id=self.table_id,
            version=record.version if version is None else version,
            action=action,
            value=value,
        )
        return (service or self.service).take_auction_step(self.actors[position], command, NOBODY_CONNECTED)

    def steps(self):
        return self.stored(self.transactions, self.table_id).progress.auction


@pytest.fixture
def hand(service, transactions, stored):
    table_id = service.create(ANNA, CreateTable(command_id="command-open")).id
    service.sit(BEN, SitDown("command-ben", table_id, 2), NOBODY_CONNECTED)
    service.sit(CLEO, SitDown("command-cleo", table_id, 3), NOBODY_CONNECTED)
    return Hand(service, transactions, stored, table_id)


def test_the_steps_read_back_in_the_order_they_were_taken(hand):
    hand.send(Position.MIDDLEHAND, AuctionAction.BID, 18, command_id=FIRST_STEP)
    hand.send(Position.FOREHAND, AuctionAction.HOLD, command_id=SECOND_STEP)
    hand.send(Position.MIDDLEHAND, AuctionAction.BID, 20, command_id="command-c")
    hand.send(Position.FOREHAND, AuctionAction.PASS, command_id="command-d")

    assert hand.steps() == (
        Bid(Position.MIDDLEHAND, 18),
        Hold(Position.FOREHAND),
        Bid(Position.MIDDLEHAND, 20),
        Pass(Position.FOREHAND),
    )


def pass_in(hand):
    """Three passes end the hand: the middlehand's and rearhand's first, the forehand's last."""
    hand.send(Position.MIDDLEHAND, AuctionAction.PASS, command_id=FIRST_STEP)
    hand.send(Position.REARHAND, AuctionAction.PASS, command_id=SECOND_STEP)
    return hand.send(Position.FOREHAND, AuctionAction.PASS, command_id=THIRD_STEP)


def test_the_third_pass_deletes_the_cards_keeps_the_steps_and_bumps_the_version_once(
    hand, engine, transactions, stored
):
    hand.send(Position.MIDDLEHAND, AuctionAction.PASS, command_id=FIRST_STEP)
    hand.send(Position.REARHAND, AuctionAction.PASS, command_id=SECOND_STEP)
    version = stored(transactions, hand.table_id).version

    hand.send(Position.FOREHAND, AuctionAction.PASS, command_id=THIRD_STEP)

    assert stored(transactions, hand.table_id).hand is None
    assert count_cards(engine) == 0
    assert hand.steps() == (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
    assert stored(transactions, hand.table_id).version == version + 1


def test_a_reload_and_a_restart_still_say_the_hand_was_passed_in(hand, database_url):
    answer = pass_in(hand)

    restarted_engine = create_store_engine(database_url)
    try:
        view = TableService(PostgresTableTransactions(restarted_engine)).view(ANNA, hand.table_id, NOBODY_CONNECTED)
    finally:
        restarted_engine.dispose()

    assert view is not None
    assert view.passed_in == answer.view.passed_in
    assert view.passed_in is not None


def test_a_failure_in_the_third_pass_keeps_the_hand_the_steps_and_the_version(hand, engine, transactions, stored):
    hand.send(Position.MIDDLEHAND, AuctionAction.PASS, command_id=FIRST_STEP)
    hand.send(Position.REARHAND, AuctionAction.PASS, command_id=SECOND_STEP)
    before = stored(transactions, hand.table_id)
    failing = TableService(FaultyTableTransactions(transactions, save_failure=ConnectionError("lost")))

    with pytest.raises(ConnectionError):
        hand.send(Position.FOREHAND, AuctionAction.PASS, command_id=THIRD_STEP, service=failing)

    assert stored(transactions, hand.table_id) == before
    assert count_cards(engine) == CARDS_IN_A_HAND
    with engine.connect() as connection:
        query = text("SELECT count(*) FROM receipts WHERE command_id = :command_id")
        receipts = connection.execute(query, {"command_id": THIRD_STEP}).scalar_one()
    assert receipts == 0


def test_two_identical_third_passes_at_once_end_the_hand_once_and_the_other_replays(hand, engine, transactions, stored):
    hand.send(Position.MIDDLEHAND, AuctionAction.PASS, command_id=FIRST_STEP)
    hand.send(Position.REARHAND, AuctionAction.PASS, command_id=SECOND_STEP)
    version = stored(transactions, hand.table_id).version
    racing = TableService(BothReadBeforeEitherWrites(transactions, 2))
    results: list[object] = []

    def request():
        results.append(
            hand.send(Position.FOREHAND, AuctionAction.PASS, command_id=THIRD_STEP, version=version, service=racing)
        )

    threads = [threading.Thread(target=request) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [result.refusal for result in results] == [None, None]
    assert sorted(bool(result.seated_when_hand_ended) for result in results) == [False, True]
    assert count_steps(engine) == 3
    assert stored(transactions, hand.table_id).version == version + 1
    assert count_cards(engine) == 0


def test_a_stand_up_between_hands_keeps_the_steps_and_the_filling_sit_replaces_them(hand, engine, transactions, stored):
    old = stored(transactions, hand.table_id)
    pass_in(hand)
    standing = hand.actors[Position.FOREHAND]
    seat = next(chair.seat for chair in old.chairs if chair.occupant.account_id == standing.account_id)
    hand.service.stand(standing, StandUp("stand", hand.table_id), NOBODY_CONNECTED)
    assert auction_of(stored(transactions, hand.table_id)).result == PassedIn()
    assert count_steps(engine) == 3
    version = stored(transactions, hand.table_id).version

    answer = hand.service.sit(DORA, SitDown("fills-the-third", hand.table_id, seat), NOBODY_CONNECTED)

    after = stored(transactions, hand.table_id)
    assert after.dealer == next_dealer(old.dealer)
    assert after.hand is not None
    assert count_cards(engine) == CARDS_IN_A_HAND
    assert after.progress == HandProgress()
    assert count_steps(engine) == 0
    assert count_rows(engine, "declaring_steps") == 0
    assert answer.view.passed_in is None
    assert after.version == version + 1


def test_the_auction_of_the_new_hand_starts_empty_in_the_store(hand, engine, transactions, stored):
    old = stored(transactions, hand.table_id)
    pass_in(hand)
    standing = hand.actors[Position.FOREHAND]
    seat = next(chair.seat for chair in old.chairs if chair.occupant.account_id == standing.account_id)
    hand.service.stand(standing, StandUp("stand", hand.table_id), NOBODY_CONNECTED)
    hand.service.sit(DORA, SitDown("fills-the-third", hand.table_id, seat), NOBODY_CONNECTED)
    after = stored(transactions, hand.table_id)
    seated_by_seat = {chair.seat: chair.occupant for chair in after.chairs}
    new_middlehand = next(
        Actor(seated_by_seat[seat_number].account_id, seated_by_seat[seat_number].display_name)
        for seat_number, position in positions_from(after.dealer).items()
        if position is Position.MIDDLEHAND
    )
    command = AuctionCommand("new-bid", hand.table_id, after.version, AuctionAction.BID, 18)

    result = hand.service.take_auction_step(new_middlehand, command, NOBODY_CONNECTED)

    assert result.refusal is None
    assert hand.steps() == (Bid(Position.MIDDLEHAND, 18),)
    assert count_steps(engine) == 1


def test_a_retry_stores_no_second_step_and_no_second_version(hand, engine, transactions, stored):
    version = stored(transactions, hand.table_id).version
    first = hand.send(Position.MIDDLEHAND, AuctionAction.BID, 18, command_id=FIRST_STEP, version=version)

    again = hand.send(Position.MIDDLEHAND, AuctionAction.BID, 18, command_id=FIRST_STEP, version=version)

    assert again == first
    assert count_steps(engine) == 1
    assert stored(transactions, hand.table_id).version == version + 1


def test_two_bids_at_once_store_exactly_one_step_and_name_the_loser_stale(hand, engine, transactions, stored):
    version = stored(transactions, hand.table_id).version
    racing = TableService(BothReadBeforeEitherWrites(transactions, 2))
    results: list[object] = []

    def request(command_id):
        results.append(
            hand.send(
                Position.MIDDLEHAND, AuctionAction.BID, 18, command_id=command_id, version=version, service=racing
            )
        )

    threads = [threading.Thread(target=request, args=(name,)) for name in (FIRST_STEP, SECOND_STEP)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert count_steps(engine) == 1
    assert sorted(str(result.refusal) for result in results) == sorted([str(None), str(Refusal.STALE_VERSION)])


def test_a_restart_reads_the_identical_steps_and_the_next_step_continues(hand, database_url, stored):
    hand.send(Position.MIDDLEHAND, AuctionAction.BID, 18, command_id=FIRST_STEP)

    restarted_engine = create_store_engine(database_url)
    try:
        restarted = PostgresTableTransactions(restarted_engine)
        assert stored(restarted, hand.table_id).progress.auction == hand.steps()
        result = hand.send(
            Position.FOREHAND,
            AuctionAction.HOLD,
            command_id=SECOND_STEP,
            service=TableService(restarted),
        )
    finally:
        restarted_engine.dispose()

    assert result.refusal is None
    assert hand.steps() == (Bid(Position.MIDDLEHAND, 18), Hold(Position.FOREHAND))


def test_a_failure_inside_the_command_stores_no_step_no_version_and_no_receipt(hand, engine, transactions, stored):
    before = stored(transactions, hand.table_id)
    failing = TableService(FaultyTableTransactions(transactions, save_failure=ConnectionError("lost")))

    with pytest.raises(ConnectionError):
        hand.send(Position.MIDDLEHAND, AuctionAction.BID, 18, command_id=FIRST_STEP, service=failing)

    assert stored(transactions, hand.table_id) == before
    assert count_steps(engine) == 0
    with engine.connect() as connection:
        receipts = connection.execute(text("SELECT count(*) FROM receipts WHERE command_id = 'command-a'")).scalar_one()
    assert receipts == 0


def test_steps_that_rewrite_a_stored_step_raise_and_change_nothing(hand, transactions, stored):
    hand.send(Position.MIDDLEHAND, AuctionAction.BID, 18, command_id=FIRST_STEP)
    before = stored(transactions, hand.table_id)
    rewritten = replace(
        before,
        version=before.version + 1,
        progress=HandProgress(auction=(Bid(Position.MIDDLEHAND, 20), Hold(Position.FOREHAND))),
    )

    def save():
        with transactions.begin() as transaction:
            transaction.save_table(rewritten, played_at=None)

    with pytest.raises(StepLogRewrittenError):
        save()

    assert stored(transactions, hand.table_id) == before


def test_steps_shorter_than_the_stored_ones_raise_and_change_nothing(hand, transactions, stored):
    hand.send(Position.MIDDLEHAND, AuctionAction.BID, 18, command_id=FIRST_STEP)
    before = stored(transactions, hand.table_id)
    shortened = replace(before, version=before.version + 1, progress=HandProgress())

    def save():
        with transactions.begin() as transaction:
            transaction.save_table(shortened, played_at=None)

    with pytest.raises(StepLogRewrittenError):
        save()

    assert stored(transactions, hand.table_id) == before


def test_a_stored_log_the_engine_refuses_raises_at_the_next_command(hand, engine):
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO auction_actions VALUES (:table_id, 1, 'rearhand', 'pass', NULL)"),
            {"table_id": hand.table_id},
        )

    with pytest.raises(ValueError, match="impossible auction log"):
        hand.send(Position.MIDDLEHAND, AuctionAction.BID, 18, command_id=FIRST_STEP)


def test_a_refused_step_keeps_its_token_in_the_receipt_for_a_retry(hand, engine):
    first = hand.send(Position.FOREHAND, AuctionAction.PASS, command_id=FIRST_STEP)
    version = first.view.version

    again = hand.send(Position.FOREHAND, AuctionAction.PASS, command_id=FIRST_STEP, version=version)

    assert again.refusal is first.refusal
    with engine.connect() as connection:
        token = connection.execute(text("SELECT refusal FROM receipts WHERE command_id = 'command-a'")).scalar_one()
    assert token == first.refusal.value
