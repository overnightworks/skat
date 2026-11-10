from sqlalchemy import func, select, table

from skat.engine.deal import Position, positions_from
from skat.engine.declaration import Announcement, Declare
from skat.engine.games import GameKind
from skat.engine.play import legal_cards
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.declaring import DeclaringCommand
from skat.table.hand_state import playing_of
from skat.table.playing import PlayCardCommand
from skat.table.records import Actor, CreateTable, SitDown, TableOptions


def person(name):
    return Actor(account_id=f"account-{name.lower()}", display_name=name)


def nobody_connected() -> frozenset[str]:
    return frozenset()


def card_id(number):
    return f"card-{number}"


def count_rows(engine, name="played_cards"):
    with engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(table(name))).scalar_one()


def seated_game(service, transactions, stored, options=None):
    """A table Anna opened with Ben and Cleo seated, ready for the auction."""
    table_id = service.create(
        person("Anna"), CreateTable(command_id="command-open", options=options or TableOptions())
    ).id
    service.sit(person("Ben"), SitDown("command-ben", table_id, 2), nobody_connected())
    service.sit(person("Cleo"), SitDown("command-cleo", table_id, 3), nobody_connected())
    return Game(service, transactions, stored, table_id)


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
