import pytest
from sqlalchemy import text

from skat.engine.cards import DECK
from skat.engine.deal import Position, positions_from
from skat.engine.ramsch import (
    DurchmarschRule,
    JungfrauRule,
    RamschOptions,
    RamschPlaying,
    RamschScoring,
    play_ramsch_card,
)
from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.hand_state import game_of
from skat.table.playing import PlayCardCommand
from skat.table.records import RamschOccasion, RamschSetting, TableOptions
from skat.table.service import TableService
from tests.support.stored_game import count_rows, nobody_connected, person, seated_table_id

pytestmark = pytest.mark.postgres

SETTING = RamschSetting(
    RamschOccasion.PASSED_IN,
    RamschOptions(RamschScoring.SKAT_TO_LOSER, JungfrauRule.OFF, DurchmarschRule.WINS_120_FLAT),
)
OPTIONS = TableOptions(ramsch=SETTING)


class RamschTable:
    """A table with Ramsch where all three passed; the cards are played legally, the first in deck order."""

    def __init__(self, service, transactions, stored):
        self.service = service
        self.transactions = transactions
        self.stored = stored
        self.table_id = seated_table_id(service, OPTIONS)
        by_seat = {1: person("Anna"), 2: person("Ben"), 3: person("Cleo")}
        self.actors = {position: by_seat[seat] for seat, position in positions_from(self.record.dealer).items()}
        for position in (Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND):
            command = AuctionCommand(
                f"pass-{position.value}", self.table_id, self.record.version, AuctionAction.PASS, None
            )
            service.take_auction_step(self.actors[position], command, nobody_connected())

    @property
    def record(self):
        return self.stored(self.transactions, self.table_id)

    def play(self, number):
        for _ in range(number):
            state = game_of(self.record)
            assert isinstance(state, RamschPlaying)
            card = next(
                each
                for each in DECK
                if each in state.hands[state.turn] and play_ramsch_card(state, state.turn, each).refusal is None
            )
            command = PlayCardCommand(
                f"card-{len(self.record.progress.plays)}", self.table_id, self.record.version, card
            )
            assert self.service.play_card(self.actors[state.turn], command, nobody_connected()).refusal is None


def restarted(database_url):
    engine = create_store_engine(database_url)
    return engine, TableService(PostgresTableTransactions(engine))


def test_a_table_reads_back_its_ramsch_options_after_a_restart(service, database_url):
    table_id = seated_table_id(service, OPTIONS)
    engine, again = restarted(database_url)
    try:
        view = again.view(person("Anna"), table_id, frozenset())
    finally:
        engine.dispose()

    assert view.options.ramsch == SETTING


def test_a_running_ramsch_resumes_after_a_restart_with_the_same_turn_and_cards(
    service, transactions, stored, database_url
):
    table = RamschTable(service, transactions, stored)
    table.play(7)
    before = service.view(table.actors[Position.FOREHAND], table.table_id, frozenset())
    engine, again = restarted(database_url)
    try:
        after = again.view(table.actors[Position.FOREHAND], table.table_id, frozenset())
        stored_cards = count_rows(engine)
    finally:
        engine.dispose()

    assert (after.hand, after.passed_in, stored_cards) == (before.hand, None, 7)
    assert after.hand.ramsch


def test_the_thirtieth_card_stores_a_ramsch_entry_and_forgets_the_hand_and_the_result_survives_a_restart(
    service, transactions, stored, database_url
):
    table = RamschTable(service, transactions, stored)
    table.play(30)
    before = service.view(table.actors[Position.FOREHAND], table.table_id, frozenset())
    engine, again = restarted(database_url)
    try:
        view = again.view(table.actors[Position.FOREHAND], table.table_id, frozenset())
        with engine.connect() as connection:
            row = connection.execute(text("SELECT kind, game, ordinal, ending, ended_by_seat FROM game_list")).one()
            cards = connection.execute(text("SELECT count(*) FROM played_cards")).scalar_one()
    finally:
        engine.dispose()

    assert (tuple(row), cards) == (("ramsch", None, 1, "played-out", None), 0)
    assert (view.hand, view.result.ordinal, len(view.result.seats)) == (None, 1, 3)
    assert view.result == before.result
