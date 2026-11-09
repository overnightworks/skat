from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.engine.bidding import Pass
from skat.engine.deal import Position, positions_from
from skat.engine.declaration import Announcement, Declare
from skat.engine.games import GameKind
from skat.engine.play import legal_cards
from skat.store.migrate import create_store_engine
from skat.store.schema import StepLogRewrittenError
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.declaring import DeclaringCommand
from skat.table.hand_state import playing_of
from skat.table.playing import PlayCardCommand
from skat.table.records import Actor, CreateTable, SitDown

pytestmark = pytest.mark.postgres

HAND_TABLES = ("hand_cards", "auction_actions", "declaring_steps", "played_cards")
NOBODY_CONNECTED = frozenset[str]()
LAST_CARD = "card-30"


def person(name):
    return Actor(account_id=f"account-{name.lower()}", display_name=name)


SEATED = (person("Anna"), person("Ben"), person("Cleo"))


class Game:
    """A seated table whose middlehand won at 18 and declared a Herz Hand game, played card by card."""

    def __init__(self, service, transactions, stored):
        self.service = service
        self.transactions = transactions
        self.stored = stored
        self.table_id = service.create(SEATED[0], CreateTable(command_id="command-open")).id
        for seat, actor in enumerate(SEATED[1:], start=2):
            service.sit(actor, SitDown(f"command-sit-{seat}", self.table_id, seat), NOBODY_CONNECTED)
        self.actors = {position: SEATED[seat - 1] for seat, position in positions_from(self.record.dealer).items()}

    @property
    def record(self):
        return self.stored(self.transactions, self.table_id)

    def bid(self, position, action, command_id, value=None):
        command = AuctionCommand(command_id, self.table_id, self.record.version, action, value)
        return self.service.take_auction_step(self.actors[position], command, NOBODY_CONNECTED)

    def declared(self):
        self.bid(Position.MIDDLEHAND, AuctionAction.BID, "bid", 18)
        self.bid(Position.FOREHAND, AuctionAction.PASS, "forehand-passes")
        self.bid(Position.REARHAND, AuctionAction.PASS, "rearhand-passes")
        declare = Declare(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.NONE)
        command = DeclaringCommand("declare", self.table_id, self.record.version, declare)
        self.service.take_declaring_step(self.actors[Position.MIDDLEHAND], command, NOBODY_CONNECTED)
        return self

    def next_card(self):
        state = playing_of(self.record)
        first = state.current[0] if state.current else None
        return state.turn, legal_cards(state.hands[state.turn], first, state.declared.declaration.kind)[0]

    def play(self, position, card, command_id, version=None):
        version = self.record.version if version is None else version
        command = PlayCardCommand(command_id, self.table_id, version, card)
        return self.service.play_card(self.actors[position], command, NOBODY_CONNECTED)

    def played_to_the_last_card(self):
        for number in range(1, 30):
            position, card = self.next_card()
            assert self.play(position, card, f"card-{number}").refusal is None
        return self.next_card()


def rows_of(engine, table_id, name):
    with engine.connect() as connection:
        return connection.execute(
            text(f"SELECT count(*) FROM {name} WHERE table_id = :table_id"),  # noqa: S608 - names come from the test's own tuple
            {"table_id": table_id},
        ).scalar_one()


def stored_list_rows(engine, table_id):
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT * FROM game_list WHERE table_id = :table_id ORDER BY ordinal"), {"table_id": table_id}
        ).all()


@pytest.fixture
def game(service, transactions, stored):
    return Game(service, transactions, stored).declared()


@pytest.fixture
def last(game):
    """The table before its thirtieth card, the card's seat and the card, and the version it is played at."""
    position, card = game.played_to_the_last_card()
    return position, card, game.record.version


@pytest.fixture
def ended(game, last):
    position, card, version = last
    assert game.play(position, card, LAST_CARD, version).refusal is None
    return game


class TestTheThirtiethCard:
    def test_writes_one_list_row_and_leaves_no_row_of_the_hand(self, ended, engine):
        assert len(stored_list_rows(engine, ended.table_id)) == 1
        assert [rows_of(engine, ended.table_id, name) for name in HAND_TABLES] == [0, 0, 0, 0]

    def test_the_stored_table_has_no_hand_no_progress_and_one_entry(self, ended):
        record = ended.record

        assert record.hand is None
        assert record.progress.plays == ()
        assert len(record.game_list) == 1

    def test_a_retry_of_the_last_card_writes_no_second_row(self, ended, engine, last):
        position, card, version = last

        again = ended.play(position, card, LAST_CARD, version)

        assert again.refusal is None
        assert len(stored_list_rows(engine, ended.table_id)) == 1

    def test_the_row_holds_the_seated_accounts_by_seat_and_every_field_of_the_entry(self, ended, engine):
        (row,) = stored_list_rows(engine, ended.table_id)
        entry = ended.record.game_list[0]

        assert (row.seat_1_account, row.seat_2_account, row.seat_3_account) == tuple(
            actor.account_id for actor in SEATED
        )
        assert (row.ordinal, row.declarer_seat, row.game, row.hand, row.ouvert, row.announcement) == (
            1,
            entry.declarer_seat,
            "herz",
            True,
            False,
            "none",
        )
        assert (row.matadors_mit, row.matadors_count) == (entry.matadors.mit, entry.matadors.count)
        assert (row.schneider, row.schwarz, row.won, row.bid) == (entry.schneider, entry.schwarz, entry.won, 18)
        assert (row.game_value, row.settled_value, row.score, row.declarer_points) == (
            entry.game_value,
            entry.settled_value,
            entry.score,
            entry.declarer_points,
        )

    def test_a_restart_reads_the_identical_list(self, ended, database_url, stored):
        restarted_engine = create_store_engine(database_url)
        try:
            restarted = stored(PostgresTableTransactions(restarted_engine), ended.table_id)
        finally:
            restarted_engine.dispose()

        assert restarted == ended.record


class TestTheList:
    def test_a_second_entry_is_stored_as_ordinal_two_and_the_first_stays(self, ended, transactions, engine):
        record = ended.record
        first = record.game_list[0]
        second = replace(first, won=not first.won)

        with transactions.begin() as transaction:
            transaction.save_table(replace(record, version=record.version + 1, game_list=(first, second)))

        assert [row.ordinal for row in stored_list_rows(engine, ended.table_id)] == [1, 2]
        assert ended.record.game_list == (first, second)

    def test_a_list_that_does_not_continue_the_stored_one_raises_and_writes_nothing(self, ended, transactions):
        before = ended.record
        rewritten = replace(before, version=before.version + 1, game_list=(replace(before.game_list[0], bid=20),))

        def save():
            with transactions.begin() as transaction:
                transaction.save_table(rewritten)

        with pytest.raises(StepLogRewrittenError):
            save()
        assert ended.record == before

    def test_the_schema_keeps_matadors_only_outside_null(self, ended, engine):
        statement = text("UPDATE game_list SET matadors_mit = NULL WHERE table_id = :table_id")

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(statement, {"table_id": ended.table_id})


class TestAPassedInHand:
    def test_keeps_its_steps_and_writes_no_entry(self, service, transactions, stored, engine):
        game = Game(service, transactions, stored)
        for number, position in enumerate((Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND)):
            game.bid(position, AuctionAction.PASS, f"pass-{number}")

        record = stored(transactions, game.table_id)
        assert record.hand is None
        assert record.progress.auction == tuple(
            Pass(position) for position in (Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND)
        )
        assert rows_of(engine, game.table_id, "game_list") == 0
        assert stored(transactions, game.table_id).game_list == ()

    def test_a_table_never_played_reads_an_empty_list(self, service, transactions, stored):
        table_id = service.create(SEATED[0], CreateTable(command_id="command-alone")).id

        assert stored(transactions, table_id).game_list == ()
