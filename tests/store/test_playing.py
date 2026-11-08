import threading
from dataclasses import replace

import pytest
from sqlalchemy import func, select, table, text
from sqlalchemy.exc import IntegrityError

from skat.engine.deal import Position, positions_from
from skat.engine.declaration import Announcement, Declare
from skat.engine.games import GameKind
from skat.engine.play import legal_cards
from skat.engine.tricks import CardPlayed, PlayRefusal
from skat.store.migrate import create_store_engine
from skat.store.schema import StepLogRewrittenError
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.declaring import DeclaringCommand
from skat.table.hand_state import playing_of
from skat.table.playing import PlayCardCommand
from skat.table.records import Actor, CreateTable, Refusal, SitDown
from skat.table.service import TableService
from tests.support.faulty_tables import BothReadBeforeEitherWrites, FaultyTableTransactions

pytestmark = pytest.mark.postgres

GAME_CARDS = 30


def person(name):
    return Actor(account_id=f"account-{name.lower()}", display_name=name)


def nobody_connected() -> frozenset[str]:
    return frozenset()


def card_id(number):
    return f"card-{number}"


def count_rows(engine):
    with engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(table("played_cards"))).scalar_one()


class Game:
    """A table whose middlehand won at 18 and declared a Herz Hand game; forehand leads."""

    def __init__(self, service, transactions, stored, table_id):
        self.service = service
        self.transactions = transactions
        self.stored = stored
        self.table_id = table_id
        by_seat = {1: person("Anna"), 2: person("Ben"), 3: person("Cleo")}
        self.actors = {position: by_seat[seat] for seat, position in positions_from(self.record.dealer).items()}
        self._auction(Position.MIDDLEHAND, AuctionAction.BID, 18, "bid")
        self._auction(Position.FOREHAND, AuctionAction.PASS, None, "forehand-passes")
        self._auction(Position.REARHAND, AuctionAction.PASS, None, "rearhand-passes")
        declare = Declare(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.NONE)
        self.service.take_declaring_step(
            self.actors[Position.MIDDLEHAND],
            DeclaringCommand(command_id="declare", table_id=table_id, version=self.record.version, step=declare),
            nobody_connected(),
        )

    @property
    def record(self):
        return self.stored(self.transactions, self.table_id)

    @property
    def plays(self):
        return self.record.progress.plays

    def _auction(self, position, action, value, command_id):
        command = AuctionCommand(
            command_id=command_id, table_id=self.table_id, version=self.record.version, action=action, value=value
        )
        self.service.take_auction_step(self.actors[position], command, nobody_connected())

    def legal_card(self):
        state = playing_of(self.record)
        first = state.current[0] if state.current else None
        return state.turn, legal_cards(state.hands[state.turn], first, state.declared.declaration.kind)[0]

    def send(self, position, card, *, command_id, version=None, service=None):
        command = PlayCardCommand(
            command_id=command_id,
            table_id=self.table_id,
            version=self.record.version if version is None else version,
            card=card,
        )
        return (service or self.service).play_card(self.actors[position], command, nobody_connected())

    def play_legally(self, number, start=1):
        for offset in range(number):
            position, card = self.legal_card()
            assert self.send(position, card, command_id=card_id(start + offset)).refusal is None


@pytest.fixture
def game(service, transactions, stored):
    table_id = service.create(person("Anna"), CreateTable(command_id="command-open")).id
    service.sit(person("Ben"), SitDown("command-ben", table_id, 2), nobody_connected())
    service.sit(person("Cleo"), SitDown("command-cleo", table_id, 3), nobody_connected())
    return Game(service, transactions, stored, table_id)


def test_the_cards_read_back_in_the_order_they_were_played(game):
    expected = []
    for number in range(1, 4):
        position, card = game.legal_card()
        expected.append(CardPlayed(position, card))
        game.send(position, card, command_id=card_id(number))

    assert game.plays == tuple(expected)


def test_a_played_card_keeps_the_dealt_hand_as_dealt(game):
    before = game.record.hand

    game.play_legally(1)

    assert game.record.hand == before


def test_thirty_cards_are_thirty_rows_and_a_thirty_first_is_refused_as_over(game, engine):
    game.play_legally(GAME_CARDS)
    before = game.record

    result = game.send(Position.FOREHAND, before.hand.hands[Position.FOREHAND][0], command_id="card-last")

    assert result.refusal.value == PlayRefusal.OVER.value
    assert count_rows(engine) == GAME_CARDS
    assert playing_of(game.record).result is not None
    assert game.record == before


def test_a_retry_stores_no_second_row_and_no_second_version(game, engine):
    position, card = game.legal_card()
    version = game.record.version
    first = game.send(position, card, command_id=card_id(1), version=version)

    again = game.send(position, card, command_id=card_id(1), version=version)

    assert again == first
    assert count_rows(engine) == 1
    assert game.record.version == version + 1


def _assert_the_receipt_keeps(game, engine, position, card, refusal):
    first = game.send(position, card, command_id=card_id(1))
    again = game.send(position, card, command_id=card_id(1))

    assert first.refusal.value == refusal.value
    assert again.refusal.value == refusal.value
    with engine.connect() as connection:
        token = connection.execute(
            text("SELECT refusal FROM receipts WHERE command_id = :command_id"), {"command_id": card_id(1)}
        ).scalar_one()
    assert token == refusal.value


def test_a_card_out_of_turn_keeps_its_token_in_the_receipt_for_a_retry(game, engine):
    position, card = game.legal_card()
    other_seat = next(each for each in Position if each is not position)

    _assert_the_receipt_keeps(game, engine, other_seat, card, PlayRefusal.NOT_YOUR_TURN)


def test_a_card_not_held_keeps_its_token_in_the_receipt_for_a_retry(game, engine):
    position, _ = game.legal_card()

    _assert_the_receipt_keeps(game, engine, position, game.record.hand.skat[0], PlayRefusal.NOT_IN_HAND)


def test_two_cards_at_once_store_exactly_one_row_and_name_the_loser_stale(game, engine, transactions):
    position, card = game.legal_card()
    version = game.record.version
    racing = TableService(BothReadBeforeEitherWrites(transactions, 2))
    results: list[object] = []

    def request(command_id):
        results.append(game.send(position, card, command_id=command_id, version=version, service=racing))

    threads = [threading.Thread(target=request, args=(name,)) for name in (card_id(1), card_id(2))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert count_rows(engine) == 1
    assert sorted(str(result.refusal) for result in results) == sorted([str(None), str(Refusal.STALE_VERSION)])


def test_a_restart_reads_the_identical_cards_and_play_continues(game, database_url, stored):
    game.play_legally(1)
    next_position, next_card = game.legal_card()

    restarted_engine = create_store_engine(database_url)
    try:
        restarted = PostgresTableTransactions(restarted_engine)
        assert stored(restarted, game.table_id).progress.plays == game.plays
        result = game.send(next_position, next_card, command_id=card_id(2), service=TableService(restarted))
    finally:
        restarted_engine.dispose()

    assert result.refusal is None
    assert len(game.plays) == 2


def test_a_failure_inside_the_command_stores_no_row_no_version_and_no_receipt(game, engine, transactions):
    before = game.record
    position, card = game.legal_card()
    failing = TableService(FaultyTableTransactions(transactions, save_failure=ConnectionError("lost")))
    command_id = card_id(1)

    with pytest.raises(ConnectionError):
        game.send(position, card, command_id=command_id, service=failing)

    assert game.record == before
    assert count_rows(engine) == 0
    with engine.connect() as connection:
        receipts = connection.execute(
            text("SELECT count(*) FROM receipts WHERE command_id = :command_id"), {"command_id": card_id(1)}
        ).scalar_one()
    assert receipts == 0


def _rewrite(transactions, record, plays):
    rewritten = replace(record, version=record.version + 1, progress=replace(record.progress, plays=plays))
    with transactions.begin() as transaction:
        transaction.save_table(rewritten)


def test_cards_that_rewrite_a_stored_card_raise_and_change_nothing(game, transactions):
    game.play_legally(1)
    before = game.record
    position, _ = game.legal_card()
    other_play = (CardPlayed(position, before.hand.skat[0]),)

    with pytest.raises(StepLogRewrittenError):
        _rewrite(transactions, before, other_play)

    assert game.record == before


def test_cards_shorter_than_the_stored_ones_raise_and_change_nothing(game, transactions):
    game.play_legally(1)
    before = game.record
    no_plays: tuple[CardPlayed, ...] = ()

    with pytest.raises(StepLogRewrittenError):
        _rewrite(transactions, before, no_plays)

    assert game.record == before


def test_the_same_card_stored_twice_raises_on_the_unique_key(game, transactions):
    game.play_legally(1)
    before = game.record
    first = before.progress.plays[0]
    repeated = (first, CardPlayed(Position.MIDDLEHAND, first.card))

    with pytest.raises(IntegrityError):
        _rewrite(transactions, before, repeated)

    assert game.record == before


def test_a_stored_log_the_engine_refuses_raises_at_the_next_command(game, engine):
    position, card = game.legal_card()
    wrong_seat = Position.REARHAND if position is not Position.REARHAND else Position.FOREHAND
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO played_cards VALUES (:table_id, 1, :position, 'hearts', 'ace')"),
            {"table_id": game.table_id, "position": wrong_seat.name.lower()},
        )

    command_id = card_id(1)

    with pytest.raises(ValueError, match="impossible card log"):
        game.send(position, card, command_id=command_id)
