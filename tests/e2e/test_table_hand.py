import json
from typing import TYPE_CHECKING

import pytest

from skat.engine.deal import positions_from
from skat.store.tables import PostgresTableTransactions
from skat.table.records import TableId
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_SIT_SUFFIX, TABLES_PATH
from tests.e2e.support.raw_http import RawSession
from tests.support.payload_cards import cards_in_text, wire_cards
from tests.support.signed_in import new_account, seed_member

if TYPE_CHECKING:
    from skat.engine.cards import Card
    from skat.table.records import TableRecord
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

CREATE_COMMAND = {"command_id": "hand-create-0001"}


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


def test_no_raw_http_body_or_stream_message_carries_a_card_its_reader_may_not_see(
    e2e_server: RunningServer,
) -> None:
    people = [signed_in(e2e_server) for _ in range(4)]
    anna, ben, cleo, _dora = people
    table_id = json.loads(anna.post(TABLES_PATH, CREATE_COMMAND))["id"]
    table_path = f"{TABLES_PATH}/{table_id}"
    ben.post(f"{table_path}{TABLE_SIT_SUFFIX}", {"command_id": "hand-sit-0002", "seat": 2})
    cleo.post(f"{table_path}{TABLE_SIT_SUFFIX}", {"command_id": "hand-sit-0003", "seat": 3})

    for person in people:
        person.get(table_path)
        person.first_stream_message(f"{table_path}{TABLE_EVENTS_SUFFIX}")
    anna.post(TABLES_PATH, CREATE_COMMAND)
    cleo.post(f"{table_path}{TABLE_SIT_SUFFIX}", {"command_id": "hand-sit-0003", "seat": 3})

    with PostgresTableTransactions(e2e_server.engine).begin() as transaction:
        stored = transaction.table(TableId(table_id))
    assert stored is not None
    assert stored.hand is not None
    for person in people:
        found = set().union(*(cards_in_text(body) for body in person.bodies))
        assert found == wire_cards(cards_held_by(stored, person.member.account.id))
        assert not found & wire_cards(stored.hand.skat)
