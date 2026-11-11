import itertools
import random
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from skat.engine.bidding import Bid, Pass
from skat.engine.deal import Position, positions_from
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.declaring import DeclaringCommand
from skat.table.playing import (
    AgreeToGiveUpCommand,
    DeclineGiveUpCommand,
    GiveUpCommand,
    PlayCardCommand,
    ThrowDownCommand,
)
from skat.table.records import Actor, CreateTable, HandProgress, SitDown, TableId
from skat.table.service import TableService
from tests.support.fake_tables import FakeTableStore
from tests.support.played_game import HERZ_HAND, before_the_last_card, declared_herz_hand

if TYPE_CHECKING:
    from skat.engine.tricks import CardPlayed

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
PEOPLE = (OPENER, VISITOR, CLEO)
ALL_THREE = frozenset(person.account_id for person in PEOPLE)
DEALT_AT = datetime(2026, 11, 1, 12, tzinfo=UTC)
LATER = DEALT_AT + timedelta(days=3)


class Scene:
    """A seeded service on a clock the test moves, with one table of three seated people and the hand dealt."""

    def __init__(self) -> None:
        self.store = FakeTableStore()
        self.now = DEALT_AT
        numbers = itertools.count(1)
        self.service = TableService(
            self.store,
            new_table_id=lambda: TableId(f"{next(numbers):032x}"),
            random_source=random.Random(1),  # noqa: S311 - a seeded source makes the deal reproducible
            now=lambda: self.now,
        )
        self.table_id = self.service.create(OPENER, CreateTable(command_id="command-open")).id
        for seat, person in ((2, VISITOR), (3, CLEO)):
            self.service.sit(person, SitDown(f"command-{seat}", self.table_id, seat), ALL_THREE)

    @property
    def table(self):
        return self.store.tables[self.table_id]

    @property
    def played_at(self):
        return self.store.last_played_at[self.table_id]

    def holder(self, position: Position) -> Actor:
        seat = {each: seat for seat, each in positions_from(self.table.dealer).items()}[position]
        return PEOPLE[seat - 1]

    def declare_herz_hand(self) -> None:
        self.store.tables[self.table_id] = replace(self.table, progress=declared_herz_hand())

    def play_to_the_last_card(self) -> CardPlayed:
        """The declared table one card before the end, where a give-up needs consent; returns the card still to play."""
        self.store.tables[self.table_id], last = before_the_last_card(self.table)
        return last

    def at(self, moment: datetime) -> Scene:
        self.now = moment
        return self


@pytest.fixture
def scene():
    return Scene()


class TestADeal:
    def test_the_third_sit_stores_the_time_of_the_deal(self, scene):
        assert scene.played_at == DEALT_AT

    def test_the_next_deal_after_a_passed_in_hand_stores_its_time(self, scene):
        steps = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
        scene.store.tables[scene.table_id] = replace(scene.table, hand=None, progress=HandProgress(steps))

        assert scene.at(LATER).service.deal_next(TableId(scene.table_id), nullcontext(ALL_THREE)) is True

        assert scene.played_at == LATER


class TestAStepOfPlay:
    @pytest.fixture(autouse=True)
    def declared(self, scene):
        scene.declare_herz_hand()
        self.version = scene.table.version

    def play_first_card(self, scene, *, position=Position.FOREHAND, version=None):
        card = scene.table.hand.hands[position][0]
        command = PlayCardCommand("command-card", scene.table_id, version or scene.table.version, card)
        return scene.service.play_card(scene.holder(position), command, ALL_THREE, on_hand_ended=lambda _: None)

    def request_give_up(self, scene, command_id="command-give-up"):
        declarer = scene.holder(Position.MIDDLEHAND)
        command = GiveUpCommand(command_id, scene.table_id, scene.table.version)
        return scene.service.give_up(declarer, command, ALL_THREE, lambda _: None)

    def test_a_played_card_moves_the_time(self, scene):
        assert self.play_first_card(scene.at(LATER)).refusal is None

        assert scene.played_at == LATER

    def test_a_give_up_that_ends_the_game_at_once_moves_the_time(self, scene):
        assert self.request_give_up(scene.at(LATER)).refusal is None

        assert scene.played_at == LATER

    def test_a_give_up_request_that_asks_for_consent_moves_the_time(self, scene):
        scene.play_to_the_last_card()

        assert self.request_give_up(scene.at(LATER)).refusal is None

        assert scene.played_at == LATER

    def test_the_agreement_to_a_give_up_moves_the_time(self, scene):
        scene.play_to_the_last_card()
        self.request_give_up(scene.at(LATER))
        command = AgreeToGiveUpCommand("command-agree", scene.table_id, scene.table.version)
        opponent = scene.holder(Position.FOREHAND)
        agreed_at = LATER + timedelta(days=1)

        result = scene.at(agreed_at).service.agree_to_give_up(opponent, command, ALL_THREE, lambda _: None)

        assert result.refusal is None
        assert scene.played_at == agreed_at

    def test_a_throw_down_moves_the_time(self, scene):
        command = ThrowDownCommand("command-throw", scene.table_id, scene.table.version)

        result = scene.at(LATER).service.throw_down(
            scene.holder(Position.MIDDLEHAND), command, ALL_THREE, lambda _: None
        )

        assert result.refusal is None
        assert scene.played_at == LATER

    def test_a_second_give_up_request_while_one_stands_leaves_the_time(self, scene):
        scene.play_to_the_last_card()
        self.request_give_up(scene.at(LATER))
        version = scene.table.version

        again = self.request_give_up(scene.at(LATER + timedelta(days=1)), "command-give-up-again")

        assert again.refusal is None
        assert (scene.table.version, scene.played_at) == (version, LATER)

    def test_the_refusal_of_a_give_up_leaves_the_time(self, scene):
        scene.play_to_the_last_card()
        self.request_give_up(scene.at(LATER))
        command = DeclineGiveUpCommand("command-decline", scene.table_id, scene.table.version)

        result = scene.at(LATER + timedelta(days=1)).service.decline_give_up(
            scene.holder(Position.FOREHAND), command, ALL_THREE
        )

        assert result.refusal is None
        assert scene.played_at == LATER

    def test_a_card_refused_for_not_being_on_turn_leaves_the_time(self, scene):
        result = self.play_first_card(scene.at(LATER), position=Position.REARHAND)

        assert result.refusal is not None
        assert scene.played_at == DEALT_AT

    def test_a_replayed_card_leaves_the_time(self, scene):
        self.play_first_card(scene.at(LATER))

        replayed = self.play_first_card(scene.at(LATER + timedelta(days=1)), version=self.version)

        assert replayed.refusal is None
        assert scene.played_at == LATER


class TestTheAuctionAndTheDeclaration:
    def test_a_bid_leaves_the_time(self, scene):
        command = AuctionCommand("command-bid", scene.table_id, scene.table.version, AuctionAction.BID, 18)

        result = scene.at(LATER).service.take_auction_step(scene.holder(Position.MIDDLEHAND), command, ALL_THREE)

        assert result.refusal is None
        assert scene.played_at == DEALT_AT

    def test_a_declaration_leaves_the_time(self, scene):
        steps = (Bid(Position.MIDDLEHAND, 18), Pass(Position.FOREHAND), Pass(Position.REARHAND))
        scene.store.tables[scene.table_id] = replace(scene.table, progress=HandProgress(auction=steps))
        command = DeclaringCommand("command-declare", scene.table_id, scene.table.version, HERZ_HAND)

        result = scene.at(LATER).service.take_declaring_step(scene.holder(Position.MIDDLEHAND), command, ALL_THREE)

        assert result.refusal is None
        assert scene.played_at == DEALT_AT
