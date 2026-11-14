"""Two agents and a person play a hand to its end: each agent's window tells the hand act by act, numbered without a
gap, and holds only the result once the hand has ended; the next hand numbers above it.
"""

import itertools

import pytest

from skat.engine.deal import Position
from tests.support.payload_cards import with_known_deal
from tests.web.support.agent import Agent
from tests.web.support.playing import HERZ_GAME, Table
from tests.web.support.series import deal_the_next_game
from tests.web.support.skat import Skat

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
FOREHAND_SEAT, MIDDLEHAND_SEAT, REARHAND_SEAT = 3, 1, 2
CARDS_OF_A_GAME = 30


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


@pytest.fixture
def skat(hold, issuer, time):
    skat = Skat(
        lambda: hold,
        issuer_transports=issuer.transports,
        chair_clock=time.clock,
        chair_scheduler=time,
        now=time.moment,
    )
    with skat.client:
        yield skat


@pytest.fixture
def mozart(skat, issuer):
    return Agent(skat, issuer, "mozart-subject", agent_name="Mozart")


@pytest.fixture
def bach(skat, issuer):
    return Agent(skat, issuer, "bach-subject", agent_name="Bach")


@pytest.fixture
def table(skat, mozart, bach):
    table = TwoAgentsTable(skat, forehand=mozart, rearhand=bach)
    table.declared_hand_game()
    return table


def numbered_without_a_gap(window):
    seqs = [line["seq"] for line in window["entries"]]
    return seqs == list(range(window["starts_at"], window["starts_at"] + len(seqs)))


class TestAHandOfTwoAgentsAndAPerson:
    def test_each_agents_window_tells_every_act_of_the_game_in_play_and_marks_only_its_own(self, table, mozart, bach):
        for played in HERZ_GAME[: CARDS_OF_A_GAME - 1]:
            table.played_by_whoever_holds_it(played)

        windows = {agent: agent.window(table.table_id) for agent in (mozart, bach)}

        for agent, window in windows.items():
            assert numbered_without_a_gap(window)
            assert [line["kind"] for line in window["entries"]] == ["deal", "bid", "pass", "pass", "declare"] + [
                "play"
            ] * (CARDS_OF_A_GAME - 1)
            assert {line["name"] for line in window["entries"] if line["own"]} == {
                f"Seat {FOREHAND_SEAT if agent is mozart else REARHAND_SEAT}"
            }

    def test_the_window_holds_only_the_result_once_the_hand_ended_and_the_next_hand_numbers_above_it(
        self, skat, table, mozart
    ):
        before = mozart.window(table.table_id)
        for played in HERZ_GAME:
            table.played_by_whoever_holds_it(played)

        ended = mozart.window(table.table_id)
        deal_the_next_game(skat, table, 1, 1)
        next_hand = mozart.window(table.table_id)

        assert [line["kind"] for line in ended["entries"]] == ["result"]
        assert ended["entries"][0]["seq"] > max(line["seq"] for line in before["entries"])
        assert [line["kind"] for line in next_hand["entries"]] == ["deal"]
        assert next_hand["starts_at"] > ended["entries"][0]["seq"]
