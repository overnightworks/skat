"""A table whose hand waits for a sitter says so in every answer, offers no step and takes a sitter over the seat."""

import pytest

from skat.table.records import Actor, SendAway
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.mcp import AUCTION_PASS_TOOL
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import with_known_deal
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import Agent
from tests.web.support.skat import Skat

SENT_SEAT = 2


class WaitingTable:
    """A dealt table with the known hand: an agent in seat 1, on turn, a second agent in seat 2 and a person in
    seat 3. The second agent is sent away by the person.
    """

    def __init__(self, skat, issuer):
        self.skat = skat
        self.staying = Agent(skat, issuer, subject="agent-staying")
        self.sent = Agent(skat, issuer, subject="agent-sent")
        self.newcomer = Agent(skat, issuer, subject="agent-newcomer")
        self.table_id = self.staying.open_table().json()["id"]
        self.sent.sit_down(self.table_id, SENT_SEAT, command_id="agent-sit-sent")
        self.person_headers, self.person = skat.member()
        skat.sit(self.person_headers, self.table_id, 3)
        with_known_deal(skat, self.table_id)

    @property
    def record(self):
        return self.skat.store.tables[self.table_id]

    def send_the_second_agent_away(self):
        sender = Actor(self.person.id, self.person.username)
        command = SendAway("command-away", self.table_id, self.skat.stores.accounts.get(self.sent.subject).id)
        result = self.skat.tables.send_away(sender, command, frozenset())
        assert result.refusal is None
        return result

    def person_reads(self):
        self.skat.client.cookies.clear()
        answer = self.skat.client.get(f"{TABLES_PATH}/{self.table_id}", headers=self.person_headers)
        assert answer.status_code == 200, answer.text
        return answer.json()

    def person_passes(self):
        self.skat.client.cookies.clear()
        return self.skat.client.post(
            f"{TABLES_PATH}/{self.table_id}{TABLE_AUCTION_PASS_SUFFIX}",
            json={"command_id": "person-pass", "version": self.record.version},
            headers={"origin": TEST_PUBLIC_ORIGIN, **self.person_headers},
        )


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


@pytest.fixture
def waiting(skat, issuer):
    table = WaitingTable(skat, issuer)
    table.send_the_second_agent_away()
    return table


class TestTheAnswersSayTheHandWaits:
    def test_the_route_and_the_tool_name_the_open_seat_the_same_for_every_viewer(self, waiting):
        seen = [
            waiting.person_reads(),
            waiting.staying.read(waiting.table_id).json(),
            waiting.sent.read(waiting.table_id).json(),
        ]

        assert [answer["hand"]["waiting_seat"] for answer in seen] == [SENT_SEAT] * 3
        assert [answer["chairs"][SENT_SEAT - 1]["occupant_name"] for answer in seen] == [None] * 3

    def test_no_value_card_or_account_is_offered_in_the_answer(self, waiting):
        answer = waiting.staying.read(waiting.table_id).json()

        assert answer["hand"]["auction"]["values"] == []
        assert waiting.person.id not in str(answer)

    def test_a_seated_agent_on_turn_is_not_awaited_and_is_again_once_a_sitter_joins(self, waiting):
        waiting_view = waiting.staying.view(waiting.table_id)

        waiting.newcomer.admitted()
        waiting.newcomer.sit_down(waiting.table_id, SENT_SEAT, command_id="agent-sit-newcomer")
        moved = waiting.staying.view(waiting.table_id)

        assert (waiting_view["awaits_you"], moved["awaits_you"]) == (False, True)
        assert moved["revision"] > waiting_view["revision"]


class TestEveryHandCommandIsRefused:
    def test_a_person_through_the_route_is_refused_seat_open(self, waiting):
        before = waiting.record

        answer = waiting.person_passes()

        assert (answer.status_code, answer.json()["reason"]) == (409, "seat-open")
        assert waiting.record == before

    def test_an_agent_through_the_tool_is_refused_seat_open(self, waiting):
        before = waiting.record

        answer = waiting.staying.call(
            AUCTION_PASS_TOOL, table_id=waiting.table_id, command_id="agent-pass", version=before.version
        )

        assert (answer.is_error, answer.json()["reason"]) == (True, "seat-open")
        assert waiting.record == before


class TestASitterTakesOver:
    def test_an_agent_by_link_sits_in_the_open_seat_and_the_hand_moves_again(self, waiting):
        waiting.newcomer.admitted()

        sat = waiting.newcomer.sit_down(waiting.table_id, SENT_SEAT, command_id="agent-sit-newcomer")

        assert not sat.is_error, sat.text
        assert sat.json()["hand"]["waiting_seat"] is None
        assert waiting.person_passes().json().get("reason") != "seat-open"

    def test_a_person_through_the_route_sits_in_the_open_seat_and_cannot_stand_up_again(self, skat, waiting):
        headers, _ = skat.member()

        sat = skat.sit(headers, waiting.table_id, SENT_SEAT, command_id="command-sit-newcomer")
        stood = skat.stand(headers, waiting.table_id, command_id="command-stand-newcomer")

        assert (sat.status_code, sat.json()["hand"]["waiting_seat"]) == (200, None)
        assert (stood.status_code, stood.json()["reason"]) == (409, "hand-running")
