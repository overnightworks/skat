import itertools

from skat.engine.deal import Position
from tests.support.payload_cards import with_known_deal
from tests.web.support.playing import Table

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
FOREHAND_SEAT, REARHAND_SEAT = 3, 2


class TwoAgentsTable(Table):
    """The known hand dealt at a table where an agent holds the forehand chair, another the rearhand chair and a
    person the middlehand chair, who declares.
    """

    def __init__(self, skat, forehand, rearhand):
        self.skat = skat
        self._commands = itertools.count(1)
        forehand_headers, rearhand_headers = forehand.admitted(), rearhand.admitted()
        person_headers = skat.member()[0]
        self.table_id = skat.create(person_headers).json()["id"]
        rearhand.sit_down(self.table_id, REARHAND_SEAT)
        forehand.sit_down(self.table_id, FOREHAND_SEAT)
        with_known_deal(skat, self.table_id)
        self.at = {FOREHAND: forehand_headers, MIDDLEHAND: person_headers, REARHAND: rearhand_headers}
        self.watcher = skat.member()[0]
        self.agents = {FOREHAND: forehand, REARHAND: rearhand}

    def played_by_whoever_holds_it(self, played):
        holder = self.holder_of(played)
        agent = self.agents.get(holder)
        if agent is None:
            self.accepted(played)
        else:
            assert not agent.play(self, played, command_id=self.fresh_id()).is_error
