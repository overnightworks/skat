import threading
from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.engine.cards import DECK
from skat.engine.deal import Position
from skat.engine.tricks import CARDS_IN_A_GAME, CardPlayed, PlayRefusal
from skat.store.migrate import create_store_engine
from skat.store.schema import StepLogRewrittenError
from skat.store.tables import PostgresTableTransactions
from skat.table.hand_state import playing_of
from skat.table.playing import (
    AgreeToGiveUpCommand,
    DeclineGiveUpCommand,
    GiveUpCommand,
    ThrowDownCommand,
)
from skat.table.records import GiveUpAsked, Refusal
from skat.table.service import TableService
from tests.support.faulty_tables import BothReadBeforeEitherWrites, FaultyTableTransactions
from tests.support.stored_game import card_id, count_rows, nobody_connected, seated_game

pytestmark = pytest.mark.postgres


@pytest.fixture
def game(service, transactions, stored):
    return seated_game(service, transactions, stored)


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


def test_a_card_after_the_thirtieth_is_refused_as_no_hand_and_leaves_no_row(game, engine):
    game.play_legally(CARDS_IN_A_GAME)
    before = game.record

    result = game.send(Position.FOREHAND, DECK[0], command_id="card-last")

    assert result.refusal == Refusal.NO_HAND
    assert count_rows(engine) == 0
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


@pytest.mark.parametrize(
    ("command_type", "run"),
    [
        pytest.param(GiveUpCommand, lambda service: service.give_up, id="give-up"),
        pytest.param(ThrowDownCommand, lambda service: service.throw_down, id="throw-down"),
    ],
)
def test_an_early_end_stores_its_entry_drops_cards_and_a_new_service_replays_the_receipt(
    game, engine, database_url, command_type, run
):
    game.play_legally(4)
    command = command_type(command_id="early-end", table_id=game.table_id, version=game.record.version)
    declarer = game.actors[Position.MIDDLEHAND]

    first = run(game.service)(declarer, command, nobody_connected(), lambda _accounts: None)

    assert first.refusal is None
    for hand_table in ("hand_cards", "auction_actions", "declaring_steps", "played_cards"):
        assert count_rows(engine, hand_table) == 0
    assert game.record.hand is None
    assert len(game.record.game_list) == 1
    restarted_engine = create_store_engine(database_url)
    try:
        again = run(TableService(PostgresTableTransactions(restarted_engine)))(
            declarer, command, nobody_connected(), lambda _accounts: None
        )
    finally:
        restarted_engine.dispose()
    assert (again.view, again.refusal) == (first.view, first.refusal)
    assert again.seated_when_hand_ended == frozenset()
    assert len(game.record.game_list) == 1


def asked_with_eight_cards(game):
    """The declarer asks to give up once he holds eight cards."""
    while len(playing_of(game.record).hands[Position.MIDDLEHAND]) > 8:
        game.play_legally(1, start=len(game.plays) + 1)
    command = GiveUpCommand(command_id="ask", table_id=game.table_id, version=game.record.version)
    result = game.service.give_up(game.actors[Position.MIDDLEHAND], command, nobody_connected(), lambda _: None)
    assert result.refusal is None


def stored_request(engine):
    with engine.connect() as connection:
        return tuple(connection.execute(text("SELECT give_up_asked_by, give_up_declined_by FROM tables")).one())


def test_an_unanswered_request_and_a_no_are_read_back_by_a_new_service_and_a_yes_after_that_ends_the_game(
    game, engine, database_url, stored
):
    asked_with_eight_cards(game)
    assert stored_request(engine) == ("middlehand", None)
    no = DeclineGiveUpCommand(command_id="no", table_id=game.table_id, version=game.record.version)
    game.service.decline_give_up(game.actors[Position.FOREHAND], no, nobody_connected())
    assert stored_request(engine) == ("middlehand", "forehand")

    restarted_engine = create_store_engine(database_url)
    try:
        restarted = PostgresTableTransactions(restarted_engine)
        assert stored(restarted, game.table_id).progress.give_up == GiveUpAsked(Position.MIDDLEHAND, Position.FOREHAND)
        yes = AgreeToGiveUpCommand(command_id="yes", table_id=game.table_id, version=game.record.version)
        result = TableService(restarted).agree_to_give_up(
            game.actors[Position.REARHAND], yes, nobody_connected(), lambda _: None
        )
    finally:
        restarted_engine.dispose()

    assert result.refusal is None
    assert game.record.hand is None
    assert len(game.record.game_list) == 1
    assert stored_request(engine) == (None, None)


def test_a_card_clears_the_stored_request(game, engine):
    asked_with_eight_cards(game)

    game.play_legally(1, start=len(game.plays) + 1)

    assert game.record.progress.give_up is None
    assert stored_request(engine) == (None, None)


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
