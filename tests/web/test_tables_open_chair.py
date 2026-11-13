"""A table whose hand waits for a sitter says so in every answer, offers no step and takes a sitter over the seat."""

from dataclasses import replace

import pytest

from skat.engine.bidding import Pass
from skat.engine.deal import Position
from skat.engine.schieberamsch import Push
from skat.table.asking import ASK_AGAIN_AFTER, ASKS_AGAIN
from skat.table.records import Actor, HandProgress, SendAway
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.mcp import AUCTION_PASS_TOOL, RAMSCH_TAKE_SKAT_TOOL
from skat.web.pushing import TABLE_PUSHING_PUSH_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import with_known_deal
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import Agent
from tests.web.support.changes import RecordedChanges
from tests.web.support.skat import Skat

SENT_SEAT = 2
PUSHING = {
    "ramsch": {
        "occasion": "passed-in",
        "scoring": "points",
        "jungfrau": "doubles-loser",
        "durchmarsch": "wins-120",
        "pushing": {"rule": "jacks-stay"},
    }
}


class WaitingTable:
    """A dealt table with the known hand: an agent in seat 1, on turn, a second agent in seat 2 and a person in
    seat 3. The second agent is sent away by the person.
    """

    def __init__(self, skat, issuer, options=None):
        self.skat = skat
        self.staying = Agent(skat, issuer, subject="agent-staying")
        self.sent = Agent(skat, issuer, subject="agent-sent")
        self.newcomer = Agent(skat, issuer, subject="agent-newcomer")
        self.table_id = self.staying.open_table(**({} if options is None else {"options": options})).json()["id"]
        self.sent.sit_down(self.table_id, SENT_SEAT, command_id="agent-sit-sent")
        self.person_headers, self.person = skat.member()
        skat.sit(self.person_headers, self.table_id, 3)
        with_known_deal(skat, self.table_id)

    def after_the_forehand_pushed_the_skat(self):
        """All three passed and the forehand, the person of seat 3, pushed the skat on: the staying agent is on turn."""
        passes = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
        self.skat.store.tables[self.table_id] = replace(
            self.record, progress=HandProgress(auction=passes, pushing=(Push(Position.FOREHAND),))
        )

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
def changes():
    return RecordedChanges()


@pytest.fixture
def skat(hold, issuer, time, changes):
    skat = Skat(
        lambda: hold,
        issuer_transports=issuer.transports,
        chair_clock=time.clock,
        chair_scheduler=time,
        now=time.moment,
        resource_changes=changes.wired,
    )
    with skat.client:
        yield skat


@pytest.fixture
def waiting(skat, issuer):
    table = WaitingTable(skat, issuer)
    table.send_the_second_agent_away()
    return table


@pytest.fixture
def waiting_in_the_pushing_stage(skat, issuer):
    table = WaitingTable(skat, issuer, PUSHING)
    table.after_the_forehand_pushed_the_skat()
    table.send_the_second_agent_away()
    return table


class TestAnOpenChairInThePushingStage:
    def test_the_answers_carry_the_open_seat_beside_the_stage_and_its_pushes_and_nobody_is_awaited(
        self, waiting_in_the_pushing_stage
    ):
        waiting = waiting_in_the_pushing_stage
        staying_view = waiting.staying.view(waiting.table_id)
        seen = [waiting.person_reads(), waiting.staying.read(waiting.table_id).json()]

        assert [answer["hand"]["waiting_seat"] for answer in seen] == [SENT_SEAT] * 2
        assert [(answer["hand"]["pushing"]["turn_seat"], answer["hand"]["pushes"]) for answer in seen] == [(1, 1)] * 2
        assert staying_view["awaits_you"] is False

    def test_a_pushing_command_is_refused_seat_open_through_the_route_and_the_tool_and_writes_nothing(
        self, waiting_in_the_pushing_stage
    ):
        waiting = waiting_in_the_pushing_stage
        before = waiting.record
        waiting.skat.client.cookies.clear()

        by_route = waiting.skat.client.post(
            f"{TABLES_PATH}/{waiting.table_id}{TABLE_PUSHING_PUSH_SUFFIX}",
            json={"command_id": "person-push", "version": before.version},
            headers={"origin": TEST_PUBLIC_ORIGIN, **waiting.person_headers},
        )
        by_tool = waiting.staying.call(
            RAMSCH_TAKE_SKAT_TOOL, table_id=waiting.table_id, command_id="agent-take", version=before.version
        )

        assert (by_route.status_code, by_route.json()["reason"]) == (409, "seat-open")
        assert (by_tool.is_error, by_tool.json()["reason"]) == (True, "seat-open")
        assert waiting.record == before

    def test_the_agent_on_turn_is_awaited_again_once_a_sitter_joins_and_the_agent_takes_the_skat(
        self, waiting_in_the_pushing_stage
    ):
        waiting = waiting_in_the_pushing_stage
        waiting.newcomer.admitted()

        waiting.newcomer.sit_down(waiting.table_id, SENT_SEAT, command_id="agent-sit-newcomer")
        awaited = waiting.staying.view(waiting.table_id)["awaits_you"]
        taken = waiting.staying.call(
            RAMSCH_TAKE_SKAT_TOOL, table_id=waiting.table_id, command_id="agent-take", version=waiting.record.version
        )

        assert awaited is True
        assert not taken.is_error, taken.text


class TestTheAnswersSayTheHandWaits:
    def test_the_route_and_the_tool_name_the_open_seat_the_same_for_every_viewer(self, waiting):
        seen = [
            waiting.person_reads(),
            waiting.staying.read(waiting.table_id).json(),
            waiting.sent.read(waiting.table_id).json(),
        ]

        assert [answer["hand"]["waiting_seat"] for answer in seen] == [SENT_SEAT] * 3
        assert [answer["chairs"][SENT_SEAT - 1]["occupant_name"] for answer in seen] == [None] * 3

    def test_every_viewer_reads_the_name_the_chair_showed_before_as_its_former_holder(self, skat, issuer):
        table = WaitingTable(skat, issuer)
        name = table.person_reads()["chairs"][SENT_SEAT - 1]["occupant_name"]
        table.send_the_second_agent_away()

        seen = [
            table.person_reads(),
            table.staying.read(table.table_id).json(),
            table.sent.read(table.table_id).json(),
        ]

        assert name
        assert [[chair["former_holder_name"] for chair in answer["chairs"]] for answer in seen] == [
            [None, name, None]
        ] * 3

    def test_a_sitter_leaves_no_former_holder(self, waiting):
        waiting.newcomer.admitted()

        sat = waiting.newcomer.sit_down(waiting.table_id, SENT_SEAT, command_id="agent-sit-newcomer")

        assert [chair["former_holder_name"] for chair in sat.json()["chairs"]] == [None] * 3

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


class TestAnOpenChairIsNotAskedAgain:
    def test_no_seat_is_asked_and_no_revision_moves_with_time_while_a_chair_is_open(self, skat, time, waiting, changes):
        first = waiting.staying.view(waiting.table_id)
        changes.told.clear()

        skat.client.portal.call(time.advance, (ASKS_AGAIN + 1) * ASK_AGAIN_AFTER)

        assert (first["awaits_you"], waiting.staying.view(waiting.table_id)["revision"], changes.told) == (
            False,
            first["revision"],
            [],
        )


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

    def test_a_person_through_the_route_sits_in_the_open_seat_and_stands_up_again_and_the_hand_waits_again(
        self, skat, waiting
    ):
        headers, _ = skat.member()

        sat = skat.sit(headers, waiting.table_id, SENT_SEAT, command_id="command-sit-newcomer")
        stood = skat.stand(headers, waiting.table_id, command_id="command-stand-newcomer")

        assert (sat.status_code, sat.json()["hand"]["waiting_seat"]) == (200, None)
        assert (stood.status_code, stood.json()["hand"]["waiting_seat"]) == (200, SENT_SEAT)

    def test_a_person_who_stood_up_is_refused_the_other_open_chair_with_a_409_and_sits_again_in_his_own(
        self, skat, waiting
    ):
        skat.stand(waiting.person_headers, waiting.table_id, command_id="command-stand-person")
        before = waiting.record

        other = skat.sit(waiting.person_headers, waiting.table_id, SENT_SEAT, command_id="command-sit-other")
        unchanged = waiting.record
        own = skat.sit(waiting.person_headers, waiting.table_id, 3, command_id="command-sit-own")

        assert (other.status_code, other.json()["reason"]) == (409, "own-seat-only")
        assert unchanged == before
        assert (own.status_code, own.json()["hand"]["waiting_seat"]) == (200, SENT_SEAT)
