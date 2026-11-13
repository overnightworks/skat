import json
from typing import TYPE_CHECKING

import pytest

from skat.engine.deal import Position, positions_from
from skat.store.tables import PostgresTableTransactions
from skat.table.records import TableId
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.declaring import (
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
)
from skat.web.tables import RANK_TOKENS, SUIT_TOKENS, TABLE_EVENTS_SUFFIX, TABLE_SIT_SUFFIX, TABLES_PATH
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.raw_http import RawSession
from tests.support.payload_cards import cards_in_text, wire_cards
from tests.support.signed_in import new_account, seed_member

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Page

    from skat.engine.cards import Card
    from skat.table.records import TableRecord
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

CREATE_COMMAND = {"command_id": "hand-create-0001", "series_length": 36}


def cards_held_by(table: TableRecord, account_id: str) -> tuple[Card, ...]:
    """The cards the database holds for the account's chair; none when the account has no chair."""
    assert table.hand is not None
    assert table.dealer is not None
    positions = positions_from(table.dealer)
    for chair in table.chairs:
        if chair.occupant is not None and chair.occupant.account_id == account_id:
            return table.hand.hands[positions[chair.seat]]
    return ()


def signed_in(server: RunningServer) -> RawSession:
    member = seed_member(server.stores, server.config, account=new_account(server.stores, server.config))
    return RawSession(server, member)


class DealtTable:
    """A table three people sat down at through the API, with a fourth who only watches."""

    def __init__(self, server: RunningServer) -> None:
        self.people = [signed_in(server) for _ in range(4)]
        anna, ben, cleo, _dora = self.people
        table_id = json.loads(anna.post(TABLES_PATH, CREATE_COMMAND))["id"]
        self.path = f"{TABLES_PATH}/{table_id}"
        ben.post(f"{self.path}{TABLE_SIT_SUFFIX}", {"command_id": "hand-sit-0002", "seat": 2})
        cleo.post(f"{self.path}{TABLE_SIT_SUFFIX}", {"command_id": "hand-sit-0003", "seat": 3})
        with PostgresTableTransactions(server.engine).begin() as transaction:
            stored = transaction.table(TableId(table_id))
        assert stored is not None
        self.stored = stored
        self.version = stored.version
        self._commands = 3

    def person_at(self, position: Position) -> RawSession:
        assert self.stored.dealer is not None
        seat = next(seat for seat, held in positions_from(self.stored.dealer).items() if held is position)
        return self.people[seat - 1]

    def look_at_it_all(self) -> None:
        for person in self.people:
            person.get(self.path)
            person.first_stream_message(f"{self.path}{TABLE_EVENTS_SUFFIX}")

    def step(self, person: RawSession, suffix: str, **fields: object) -> None:
        self._commands += 1
        answer = person.post(
            f"{self.path}{suffix}",
            {"command_id": f"hand-step-{self._commands:04d}", "version": self.version, **fields},
        )
        self.version = json.loads(answer)["version"]

    def middlehand_wins(self) -> RawSession:
        declarer = self.person_at(Position.MIDDLEHAND)
        self.step(declarer, TABLE_AUCTION_BID_SUFFIX, value=18)
        self.step(self.person_at(Position.FOREHAND), TABLE_AUCTION_PASS_SUFFIX)
        self.step(self.person_at(Position.REARHAND), TABLE_AUCTION_PASS_SUFFIX)
        return declarer

    def cards_seen_by(self, person: RawSession) -> set[tuple[str, str]]:
        return set().union(*(cards_in_text(body) for body in person.bodies))

    def last_declaring_of(self, person: RawSession) -> dict[str, object]:
        return json.loads(person.bodies[-1].removeprefix("data: "))["hand"]["declaring"]


def card_on_the_wire(card: Card) -> dict[str, str]:
    return {"suit": SUIT_TOKENS[card.suit], "rank": RANK_TOKENS[card.rank]}


def test_no_raw_http_body_or_stream_message_carries_a_card_its_reader_may_not_see(
    e2e_server: RunningServer,
) -> None:
    table = DealtTable(e2e_server)
    table.look_at_it_all()
    anna, _ben, cleo, _dora = table.people
    anna.post(TABLES_PATH, CREATE_COMMAND)
    cleo.post(f"{table.path}{TABLE_SIT_SUFFIX}", {"command_id": "hand-sit-0003", "seat": 3})
    table.step(table.person_at(Position.MIDDLEHAND), TABLE_AUCTION_BID_SUFFIX, value=18)
    table.look_at_it_all()
    assert table.stored.hand is not None
    for person in table.people:
        found = table.cards_seen_by(person)
        assert found == wire_cards(cards_held_by(table.stored, person.member.account.id))
        assert not found & wire_cards(table.stored.hand.skat)


def test_the_skat_reaches_only_the_declarer_after_the_take_and_no_other_raw_payload(
    e2e_server: RunningServer,
) -> None:
    table = DealtTable(e2e_server)
    declarer = table.middlehand_wins()
    table.look_at_it_all()
    table.step(declarer, TABLE_DECLARING_TAKE_SUFFIX)
    table.look_at_it_all()
    assert table.stored.hand is not None
    dealt = cards_held_by(table.stored, declarer.member.account.id)
    table.step(
        declarer,
        TABLE_DECLARING_PUT_BACK_SUFFIX,
        cards=[card_on_the_wire(card) for card in dealt[:2]],
    )
    table.look_at_it_all()
    table.step(declarer, TABLE_DECLARING_DECLARE_SUFFIX, game="herz", hand=False, ouvert=False, announcement="none")
    table.look_at_it_all()

    for person in table.people:
        held = wire_cards(cards_held_by(table.stored, person.member.account.id))
        allowed = held | wire_cards(table.stored.hand.skat) if person is declarer else held
        assert table.cards_seen_by(person) == allowed
        assert table.last_declaring_of(person)["stage"] == "declared"


def test_a_hand_games_skat_stays_out_of_every_raw_payload_at_every_stage(e2e_server: RunningServer) -> None:
    table = DealtTable(e2e_server)
    declarer = table.middlehand_wins()
    table.look_at_it_all()
    table.step(declarer, TABLE_DECLARING_DECLARE_SUFFIX, game="herz", hand=True, ouvert=False, announcement="none")
    table.look_at_it_all()

    for person in table.people:
        assert table.cards_seen_by(person) == wire_cards(cards_held_by(table.stored, person.member.account.id))
        assert table.last_declaring_of(person)["stage"] == "declared"


@pytest.mark.parametrize("width", [320, 900, 1000])
def test_a_hand_in_play_fits_the_screen_width_so_the_page_never_scrolls_sideways(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    width: int,
) -> None:
    table = deal_playing_table(
        open_person,
        e2e_server,
        member_of,
        page_errors,
        {"viewport": {"width": width, "height": 800}, "is_mobile": width == 320, "has_touch": width == 320},
    )
    for person in table.pages.values():
        measured = person.evaluate("() => [innerWidth, document.documentElement.scrollWidth]")
        assert measured == [width, width]
