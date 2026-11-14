import random
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from operator import attrgetter

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from skat.engine.bidding import Pass
from skat.engine.deal import Position, positions_from
from skat.engine.declaration import Announcement, Declaration, Declare
from skat.engine.games import GameKind
from skat.engine.kontra import KontraReach
from skat.engine.play import legal_cards
from skat.engine.tricks import CardPlayed
from skat.engine.value import Matadors
from skat.store.game_list import read_game_cards
from skat.store.migrate import create_store_engine
from skat.store.schema import StepLogRewrittenError
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.declaring import DeclaringCommand
from skat.table.game_list import GameEnding, ListEntry, RamschEntry, standings_of
from skat.table.hand_state import playing_of
from skat.table.playing import PlayCardCommand
from skat.table.records import Actor, CreateTable, SitDown
from skat.table.service import TableService
from tests.support.played_game import a_game_cards

pytestmark = pytest.mark.postgres

HAND_TABLES = ("hand_cards", "auction_actions", "declaring_steps", "played_cards")
NOBODY_CONNECTED = frozenset[str]()
LAST_CARD = "card-30"
FINISHED_AT = datetime(2026, 11, 11, 20, 15, tzinfo=UTC)


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


def an_entry(declaration, **numbers):
    fields = {
        "seat_accounts": tuple(actor.account_id for actor in SEATED),
        "seat_names": tuple(actor.display_name for actor in SEATED),
        "declarer_seat": 2,
        "schneider": False,
        "schwarz": False,
        "matadors": Matadors(mit=True, count=2),
        "kontra_word": None,
        "bock_factor": 1,
        "ending": GameEnding.PLAYED_OUT,
        "ended_by_seat": None,
        **numbers,
    }
    return ListEntry(declaration=declaration, **fields)


END_OVER = an_entry(
    Declaration(GameKind.KARO, hand=False, ouvert=False, announcement=Announcement.NONE),
    matadors=Matadors(mit=True, count=1),
    won=False,
    bid=20,
    game_value=18,
    settled_value=27,
    score=-54,
    declarer_points=70,
)
A_NULL = an_entry(
    Declaration(GameKind.NULL, hand=False, ouvert=False, announcement=Announcement.NONE),
    matadors=None,
    won=True,
    bid=23,
    game_value=23,
    settled_value=23,
    score=23,
    declarer_points=0,
)
OUVERT_HAND = an_entry(
    Declaration(GameKind.PIK, hand=True, ouvert=True, announcement=Announcement.SCHWARZ),
    matadors=Matadors(mit=False, count=3),
    schneider=True,
    schwarz=True,
    won=True,
    bid=24,
    game_value=110,
    settled_value=110,
    score=110,
    declarer_points=120,
)


GIVEN_UP = replace(END_OVER, ending=GameEnding.GIVEN_UP, ended_by_seat=2)
THROWN_DOWN = replace(OUVERT_HAND, ending=GameEnding.THROWN_DOWN, ended_by_seat=3)


def a_ramsch_entry(**numbers):
    fields = {
        "seat_accounts": tuple(actor.account_id for actor in SEATED),
        "seat_names": tuple(actor.display_name for actor in SEATED),
        "seat_points": (12, 40, 68),
        "seat_scores": (-12, -40, -68),
        "durchmarsch_seat": None,
        "jungfrau": False,
        "bock_factor": 1,
        "pushes": 0,
        **numbers,
    }
    return RamschEntry(**fields)


A_RAMSCH = a_ramsch_entry()
A_DURCHMARSCH = a_ramsch_entry(seat_points=(120, 0, 0), seat_scores=(120, -7, -9), durchmarsch_seat=1)
A_JUNGFRAU = a_ramsch_entry(seat_points=(0, 50, 70), seat_scores=(-4, -25, -35), jungfrau=True)
A_BOCK_RAMSCH = a_ramsch_entry(seat_scores=(-24, -80, -136), bock_factor=2)
A_RAMSCH_IN_TWO_ROUNDS = a_ramsch_entry(seat_scores=(-48, -160, -272), bock_factor=4)


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
def clocked_game(transactions, stored):
    clocked = TableService(transactions, random_source=random.Random(8), now=lambda: FINISHED_AT)  # noqa: S311 - seeded
    return Game(clocked, transactions, stored).declared()


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
        assert list(map(partial(rows_of, engine, ended.table_id), HAND_TABLES)) == [0, 0, 0, 0]

    def test_the_stored_table_has_no_hand_no_progress_and_one_entry(self, ended):
        record = ended.record

        assert record.hand is None
        assert record.progress.plays == ()
        assert len(record.game_list) == 1

    def test_the_row_holds_the_series_number_and_the_instant_of_the_command_that_played_the_last_card(
        self, clocked_game, engine
    ):
        position, card = clocked_game.played_to_the_last_card()
        assert clocked_game.play(position, card, LAST_CARD).refusal is None

        (row,) = stored_list_rows(engine, clocked_game.table_id)

        assert (row.series_number, row.finished_at) == (1, FINISHED_AT)

    def test_a_list_insert_that_fails_keeps_the_hand_the_version_and_the_receipts_as_they_were(
        self, game, last, engine
    ):
        position, card, version = last
        before = game.record
        hand_rows = list(map(partial(rows_of, engine, game.table_id), HAND_TABLES))
        receipts = rows_of(engine, game.table_id, "receipts")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE FUNCTION refuse_list_rows() RETURNS trigger LANGUAGE plpgsql"
                    " AS $$ BEGIN RAISE EXCEPTION 'the list refuses this row'; END $$"
                )
            )
            connection.execute(
                text(
                    "CREATE TRIGGER refuse_list_rows BEFORE INSERT ON game_list"
                    " FOR EACH ROW EXECUTE FUNCTION refuse_list_rows()"
                )
            )

        with pytest.raises(DBAPIError):
            game.play(position, card, LAST_CARD, version)

        assert game.record == before
        assert len(stored_list_rows(engine, game.table_id)) == 0
        assert list(map(partial(rows_of, engine, game.table_id), HAND_TABLES)) == hand_rows
        assert rows_of(engine, game.table_id, "receipts") == receipts

    def test_a_retry_of_the_last_card_writes_no_second_row(self, ended, engine, last):
        position, card, version = last

        again = ended.play(position, card, LAST_CARD, version)

        assert again.refusal is None
        assert len(stored_list_rows(engine, ended.table_id)) == 1

    def test_the_row_holds_the_seated_accounts_by_seat_and_every_field_of_the_entry(self, ended, engine):
        (row,) = stored_list_rows(engine, ended.table_id)
        entry = ended.record.game_list[0]

        assert attrgetter("seat_1_account", "seat_2_account", "seat_3_account")(row) == tuple(
            actor.account_id for actor in SEATED
        )
        assert attrgetter("seat_1_name", "seat_2_name", "seat_3_name")(row) == tuple(
            actor.display_name for actor in SEATED
        )
        assert attrgetter("ordinal", "declarer_seat", "game", "hand", "ouvert", "announcement")(row) == (
            1,
            entry.declarer_seat,
            "herz",
            True,
            False,
            "none",
        )
        assert attrgetter("matadors_mit", "matadors_count")(row) == (entry.matadors.mit, entry.matadors.count)
        assert attrgetter("schneider", "schwarz", "won", "bid")(row) == (entry.schneider, entry.schwarz, entry.won, 18)
        assert attrgetter("game_value", "settled_value", "score", "declarer_points")(row) == (
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


def stored_cards(engine, table_id, number=1):
    with engine.connect() as connection:
        return read_game_cards(connection, table_id, number)


class TestTheCardsOfTheGame:
    def test_the_thirtieth_card_stores_every_card_of_the_game_for_a_restart_to_read(self, game, last, database_url):
        position, card, version = last
        plays = (*game.record.progress.plays, CardPlayed(position, card))
        seats = {each: SEATED.index(actor) + 1 for each, actor in game.actors.items()}
        game.play(position, card, LAST_CARD, version)

        restarted_engine = create_store_engine(database_url)
        try:
            cards = stored_cards(restarted_engine, game.table_id)
        finally:
            restarted_engine.dispose()

        assert [(each.seat, each.card) for trick in cards.tricks for each in trick] == [
            (seats[play.position], play.card) for play in plays
        ]
        assert [len(hand) for hand in cards.hands] == [10, 10, 10]
        assert (len(cards.skat), cards.put_away) == (2, ())

    def test_the_cards_are_written_in_the_transaction_of_the_entry(self, game, last, engine):
        position, card, version = last
        before = game.record
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE FUNCTION refuse_card_rows() RETURNS trigger LANGUAGE plpgsql"
                    " AS $$ BEGIN RAISE EXCEPTION 'the cards refuse this row'; END $$"
                )
            )
            connection.execute(
                text(
                    "CREATE TRIGGER refuse_card_rows BEFORE INSERT ON game_cards"
                    " FOR EACH ROW EXECUTE FUNCTION refuse_card_rows()"
                )
            )

        with pytest.raises(DBAPIError):
            game.play(position, card, LAST_CARD, version)

        assert game.record == before
        assert len(stored_list_rows(engine, game.table_id)) == 0

    @pytest.mark.parametrize(
        ("second", "cards"),
        [
            pytest.param(replace(END_OVER, cards=a_game_cards()), a_game_cards(), id="an-entry-with-cards"),
            pytest.param(END_OVER, None, id="an-entry-without-cards"),
        ],
    )
    def test_a_second_entry_stores_the_cards_it_carries_and_no_others(self, ended, transactions, engine, second, cards):
        record = ended.record
        first = record.game_list[0]

        with transactions.begin() as transaction:
            transaction.save_table(
                replace(record, version=record.version + 1, game_list=(first, second)), played_at=None
            )

        assert ended.record.game_list == (first, second)
        assert stored_cards(engine, ended.table_id, 2) == cards

    def test_a_number_outside_the_list_has_no_cards(self, ended, engine):
        assert stored_cards(engine, ended.table_id, 7) is None


class TestTheList:
    def test_a_second_entry_is_stored_as_ordinal_two_and_the_first_stays(self, ended, transactions, engine):
        record = ended.record
        first = record.game_list[0]
        second = replace(first, won=not first.won)

        with transactions.begin() as transaction:
            transaction.save_table(
                replace(record, version=record.version + 1, game_list=(first, second)), played_at=None
            )

        assert list(map(attrgetter("ordinal"), stored_list_rows(engine, ended.table_id))) == [1, 2]
        assert ended.record.game_list == (first, second)

    @pytest.mark.parametrize(
        ("entry", "played_at"),
        [
            (END_OVER, FINISHED_AT),
            (GIVEN_UP, FINISHED_AT),
            (THROWN_DOWN, FINISHED_AT),
            (A_RAMSCH, FINISHED_AT),
            (END_OVER, None),
        ],
        ids=["played-out", "given-up", "thrown-down", "ramsch", "no-instant-saved"],
    )
    def test_an_entry_is_stored_with_the_instant_of_the_save_that_wrote_it_and_null_without_one(
        self, ended, transactions, engine, entry, played_at
    ):
        record = ended.record

        with transactions.begin() as transaction:
            transaction.save_table(
                replace(record, version=record.version + 1, game_list=(*record.game_list, entry)), played_at=played_at
            )

        assert stored_list_rows(engine, ended.table_id)[1].finished_at == played_at

    def test_a_list_that_does_not_continue_the_stored_one_raises_and_writes_nothing(self, ended, transactions):
        before = ended.record
        rewritten = replace(before, version=before.version + 1, game_list=(replace(before.game_list[0], bid=20),))

        def save():
            with transactions.begin() as transaction:
                transaction.save_table(rewritten, played_at=None)

        with pytest.raises(StepLogRewrittenError):
            save()
        assert ended.record == before

    def test_a_person_who_left_is_ranked_by_the_name_the_list_stored_for_them(self, ended, transactions):
        record = ended.record
        first = record.game_list[0]
        sat_again = replace(first, seat_accounts=(*first.seat_accounts[:1], "account-dora", first.seat_accounts[2]))
        sat_again = replace(sat_again, seat_names=("Anna", "Dora", "Cleo"))

        with transactions.begin() as transaction:
            transaction.save_table(
                replace(record, version=record.version + 1, game_list=(first, sat_again)), played_at=None
            )

        names = {
            each.account_id: each.display_name for each in standings_of(ended.record.game_list, KontraReach.KONTRA_RE)
        }
        assert names == {"account-anna": "Anna", "account-ben": "Ben", "account-cleo": "Cleo", "account-dora": "Dora"}

    def test_an_entry_stored_without_names_reads_back_without_names(self, ended, transactions):
        record = ended.record
        nameless = replace(record.game_list[0], seat_names=(None, None, None))

        with transactions.begin() as transaction:
            transaction.save_table(
                replace(record, version=record.version + 1, game_list=(*record.game_list, nameless)), played_at=None
            )

        assert ended.record.game_list[1].seat_names == (None, None, None)
        assert {each.display_name for each in standings_of(ended.record.game_list, KontraReach.KONTRA_RE)} == {None}

    @pytest.mark.parametrize(
        "entry",
        [END_OVER, A_NULL, OUVERT_HAND, GIVEN_UP, THROWN_DOWN],
        ids=["end-over", "null", "ouvert-hand", "given-up", "thrown-down"],
    )
    def test_an_entry_reads_back_as_built_with_its_own_numbers_in_the_row(self, ended, transactions, engine, entry):
        record = ended.record

        with transactions.begin() as transaction:
            transaction.save_table(
                replace(record, version=record.version + 1, game_list=(*record.game_list, entry)), played_at=None
            )

        assert ended.record.game_list[1] == entry
        row = stored_list_rows(engine, ended.table_id)[1]
        assert attrgetter("ordinal", "bid", "game_value", "settled_value", "score")(row) == (
            2,
            entry.bid,
            entry.game_value,
            entry.settled_value,
            entry.score,
        )
        stored_matadors = None if row.matadors_mit is None else (row.matadors_mit, row.matadors_count)
        built_matadors = None if entry.matadors is None else (entry.matadors.mit, entry.matadors.count)
        assert stored_matadors == built_matadors

    @pytest.mark.parametrize(
        "entry",
        [A_RAMSCH, A_DURCHMARSCH, A_JUNGFRAU, A_BOCK_RAMSCH, A_RAMSCH_IN_TWO_ROUNDS],
        ids=["plain", "durchmarsch", "jungfrau", "bock", "two-rounds"],
    )
    def test_a_ramsch_entry_after_a_declared_one_reads_back_as_written(self, ended, transactions, entry):
        record = ended.record

        with transactions.begin() as transaction:
            transaction.save_table(
                replace(record, version=record.version + 1, game_list=(*record.game_list, entry)), played_at=None
            )

        assert ended.record.game_list == (*record.game_list, entry)

    @pytest.mark.parametrize(
        ("entry", "columns"),
        [
            pytest.param(END_OVER, ("played-out", None), id="played-out"),
            pytest.param(GIVEN_UP, ("given-up", 2), id="given-up"),
            pytest.param(THROWN_DOWN, ("thrown-down", 3), id="thrown-down"),
            pytest.param(A_RAMSCH, ("played-out", None), id="a-ramsch-is-played-out"),
        ],
    )
    def test_the_row_holds_the_ending_and_the_seat_as_text_and_number(
        self, ended, transactions, engine, entry, columns
    ):
        record = ended.record

        with transactions.begin() as transaction:
            transaction.save_table(
                replace(record, version=record.version + 1, game_list=(*record.game_list, entry)), played_at=None
            )

        row = stored_list_rows(engine, ended.table_id)[1]
        assert columns == (row.ending, row.ended_by_seat)

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
