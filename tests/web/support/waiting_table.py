"""A dealt table whose second agent can be sent away, for the tests of an open chair."""

from dataclasses import replace

from skat.engine.bidding import Pass
from skat.engine.deal import Position
from skat.engine.schieberamsch import Push
from skat.table.records import Actor, HandProgress, SendAway
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import with_known_deal
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import Agent

SENT_SEAT = 2


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
        result = self.skat.tables.send_away(sender, command, frozenset({sender.account_id}), is_member=True)
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
