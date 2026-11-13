import itertools
import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.engine.cards import Card
from skat.engine.games import GameKind
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import RANK_TOKENS, SUIT_TOKENS
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import DEFAULT_JOINERS, DEFAULT_OPENER, DeclaringTable
from tests.e2e.support.people import PERSON_ADDRESS_BASE, person_address_offsets
from tests.e2e.support.raw_http import RawSession

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

WE = text(SOURCE_LANGUAGE, "play.sideUs")
THEY = text(SOURCE_LANGUAGE, "play.sideThem")
TURN_CHAIR = ".chair.turn"

command_numbers = itertools.count(1)

type WireCard = tuple[str, str]


class AddressedSession(RawSession):
    """A raw session from an address of its own, as a person behind a proxy: the server's budget is per address."""

    def __init__(self, server: RunningServer, member: SeededMember) -> None:
        super().__init__(server, member)
        self._address = str(PERSON_ADDRESS_BASE + next(person_address_offsets))

    def _headers(self) -> dict[str, str]:
        return {**super()._headers(), "x-forwarded-for": self._address}


class PlayingTable:
    """A declared game, named or already declared on the page: the forehand leads, and every card is read by API."""

    def __init__(self, declaring: DeclaringTable, game: str | None) -> None:
        self.declaring = declaring
        self.game = None if game is None else GameKind[game.upper()]
        declaring.sessions = {
            seat: AddressedSession(declaring.server, session.member) for seat, session in declaring.sessions.items()
        }
        if game is not None:
            skat = declaring.skat()
            declaring.declare_through_the_api(action="take")
            declaring.declare_through_the_api(
                action="put_back", cards=[{"suit": suit, "rank": rank} for suit, rank in sorted(skat)]
            )
            declaring.declare_through_the_api(
                action="declare", game=game, hand=False, ouvert=False, announcement="none"
            )
        self.watcher = declaring.watcher
        self.declarer_seat = declaring.declarer_seat
        self.pages = {self.seat_of(person): person for person in (declaring.declarer, *declaring.others)}
        self.everyone = [*self.pages.values(), self.watcher]
        chairs = self.view(self.declarer_seat)["chairs"]
        self.names = {chair["seat"]: chair["occupant_name"] for chair in chairs}
        self.seat_at = {chair["hand"]["position"]: chair["seat"] for chair in chairs}
        for person in self.everyone:
            expect(person.locator(TURN_CHAIR)).to_have_attribute("data-seat", str(self.seat_at["forehand"]))

    @staticmethod
    def seat_of(person: Page) -> int:
        return int(person.locator(".chair.mine").get_attribute("data-seat") or "")

    def view(self, seat: int) -> dict[str, Any]:
        return json.loads(self.declaring.sessions[seat].get(self.declaring.api_path))

    def playing(self) -> dict[str, Any]:
        return self.view(self.declarer_seat)["hand"]["playing"]

    def turn_seat(self) -> int:
        return self.playing()["turn_seat"]

    def own_cards(self, seat: int) -> list[WireCard]:
        return [(card["suit"], card["rank"]) for card in self.view(seat)["hand"]["own_cards"]]

    def legal_cards(self, seat: int) -> set[WireCard]:
        return {(card["suit"], card["rank"]) for card in self.view(seat)["hand"]["playing"]["legal_cards"]}

    def led_card(self) -> WireCard:
        led = self.playing()["current_trick"][0]["card"]
        return led["suit"], led["rank"]

    def _send(self, seat: int, version: int, card: WireCard) -> dict[str, Any]:
        suit, rank = card
        command_id = f"playing-card-{next(command_numbers):04d}"
        body = {"command_id": command_id, "version": version, "suit": suit, "rank": rank}
        return json.loads(self.declaring.sessions[seat].post(f"{self.declaring.api_path}{TABLE_CARD_SUFFIX}", body))

    def play_through_the_api(self, card: WireCard) -> None:
        view = self.view(self.declarer_seat)
        self._send(view["hand"]["playing"]["turn_seat"], view["version"], card)

    def play_out(self, cards: int) -> None:
        """Each seat on turn plays its first legal card, two requests a card.

        The thirtieth card ends the hand, and nothing is left to play.
        """
        seat = self.turn_seat()
        for _ in range(cards):
            view = self.view(seat)
            legal = sorted((card["suit"], card["rank"]) for card in view["hand"]["playing"]["legal_cards"])
            hand = self._send(seat, view["version"], legal[0])["hand"]
            if hand is None:
                return
            seat = hand["playing"]["turn_seat"]

    def result(self) -> dict[str, Any]:
        return self.view(self.declarer_seat)["result"]

    def ready_through_the_api(self, seat: int) -> None:
        """„Weiter“ for the result the seat's own view shows."""
        command_id = f"playing-ready-{next(command_numbers):04d}"
        body = {"command_id": command_id, "ordinal": self.view(seat)["result"]["ordinal"]}
        self.declaring.sessions[seat].post(f"{self.declaring.api_path}{TABLE_READY_SUFFIX}", body)

    def a_lead_the_middlehand_must_follow(self) -> WireCard:
        """A forehand card whose playing suit the middlehand holds beside another (Kreuz: jacks and Kreuz are trump)."""
        held = {self._playing_suit(card) for card in self.own_cards(self.seat_at["middlehand"])}
        for card in self.own_cards(self.seat_at["forehand"]):
            if self._playing_suit(card) in held and len(held) > 1:
                return card
        pytest.fail("the deal gave the forehand no suit the middlehand must follow")

    def _playing_suit(self, card: WireCard) -> object:
        assert self.game is not None, "a table whose game was declared on the page has no named game"
        suits = {token: suit for suit, token in SUIT_TOKENS.items()}
        ranks = {token: rank for rank, token in RANK_TOKENS.items()}
        return self.game.playing_suit(Card(suits[card[0]], ranks[card[1]]))


def deal_playing_table(
    open_person: Callable[..., Page],
    server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
    *,
    console: bool = True,
    game: str = "kreuz",
    declaring: type[DeclaringTable] = DeclaringTable,
    joiners: tuple[str, str] = DEFAULT_JOINERS,
    opener_name: str = DEFAULT_OPENER,
) -> PlayingTable:
    table = declaring(
        open_person,
        server,
        member_of,
        page_errors,
        form_factor,
        console=console,
        joiners=joiners,
        opener_name=opener_name,
    )
    return PlayingTable(table, game)
