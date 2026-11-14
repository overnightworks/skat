import pytest

from skat.engine.deal import Position
from skat.engine.tricks import PlayRefusal
from skat.table.records import Refusal
from skat.web.playing import (
    TABLE_GIVE_UP_SUFFIX,
    TABLE_PLAY_OPEN_SUFFIX,
    TABLE_SHORTEN_SUFFIX,
    TABLE_THROW_DOWN_SUFFIX,
)
from tests.web.support.giving_up import SEAT, playing_as
from tests.web.support.open_play import (
    NINE_TRICKS,
    asked_to_play_open,
    open_play_read,
    plays_open,
    waiting_for,
)
from tests.web.support.playing import HERZ_GAME, Table
from tests.web.support.shortening import (
    everyone,
    shortens,
)

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
OPPONENTS = [pytest.param(FOREHAND, id="forehand"), pytest.param(REARHAND, id="rearhand")]


@pytest.fixture
def table(skat):
    return Table(skat)


@pytest.fixture
def herz_hand(table):
    table.declared_hand_game()
    return table


class TestTheDeclarerCouldTakeNoFurtherTrick:
    @pytest.mark.parametrize("position", OPPONENTS)
    def test_the_game_ends_at_once_by_the_opponents_seat_and_every_viewer_reads_the_ending(self, herz_hand, position):
        herz_hand.played_out(NINE_TRICKS)

        answer = plays_open(herz_hand, position)

        assert answer.status_code == 200, answer.text
        assert herz_hand.record.hand is None
        assert herz_hand.endings_in_every_view() == {("played-open", SEAT[position])}
        assert answer.json()["result"]["declarer_points"] == herz_hand.result()["declarer_points"]

    def test_the_rest_of_the_game_goes_to_the_opponents(self, herz_hand):
        herz_hand.played_out(NINE_TRICKS)

        plays_open(herz_hand, FOREHAND)

        result = herz_hand.result()
        assert result["declarer_points"] + result["opponents_points"] == 120
        (entry,) = herz_hand.record.game_list
        assert entry.declarer_points == result["declarer_points"]

    def test_a_retry_with_the_same_id_and_version_ends_the_game_once(self, herz_hand):
        herz_hand.played_out(NINE_TRICKS)
        body = {"command_id": "command-open", "version": herz_hand.record.version}
        first = plays_open(herz_hand, FOREHAND, body=body)
        stored = herz_hand.record

        again = plays_open(herz_hand, FOREHAND, body=body)

        assert (again.status_code, again.json()) == (200, first.json())
        assert herz_hand.record == stored


class TestAWrongOpenPlay:
    def test_the_declarer_is_asked_and_every_viewer_reads_who_played_open_and_no_card_moves(self, herz_hand):
        before = herz_hand.record

        answer = asked_to_play_open(herz_hand, FOREHAND)

        assert herz_hand.record.version == before.version + 1
        assert herz_hand.record.hand is not None
        assert herz_hand.record.game_list == ()
        assert answer.json()["hand"]["playing"]["open_play_seat"] == SEAT[FOREHAND]
        assert open_play_read(herz_hand) == waiting_for(FOREHAND)
        assert everyone(herz_hand, lambda each, headers: playing_as(each, headers)["give_up"]) == [None] * 4

    def test_while_the_declarer_decides_no_card_throw_down_give_up_or_shortening_is_taken(self, herz_hand):
        asked_to_play_open(herz_hand, FOREHAND)

        for suffix, position in (
            (TABLE_THROW_DOWN_SUFFIX, MIDDLEHAND),
            (TABLE_SHORTEN_SUFFIX, MIDDLEHAND),
            (TABLE_PLAY_OPEN_SUFFIX, REARHAND),
        ):
            herz_hand.refused_act(suffix, herz_hand.at[position], Refusal.REQUEST_PENDING)
        herz_hand.refused(herz_hand.at[FOREHAND], HERZ_GAME[0], Refusal.REQUEST_PENDING)


class TestWhoMayPlayOpen:
    def test_the_declarer_cannot_play_open_and_nothing_changes(self, herz_hand):
        herz_hand.refused_act(TABLE_PLAY_OPEN_SUFFIX, herz_hand.at[MIDDLEHAND], PlayRefusal.NOT_AN_OPPONENT)

    def test_a_standing_give_up_of_the_declarer_is_pending(self, herz_hand):
        herz_hand.played_out(HERZ_GAME[:4])
        assert herz_hand.act(TABLE_GIVE_UP_SUFFIX).status_code == 200

        herz_hand.refused_act(TABLE_PLAY_OPEN_SUFFIX, herz_hand.at[FOREHAND], Refusal.REQUEST_PENDING)

    def test_a_standing_shortening_is_pending(self, herz_hand):
        shortens(herz_hand)

        herz_hand.refused_act(TABLE_PLAY_OPEN_SUFFIX, herz_hand.at[FOREHAND], Refusal.REQUEST_PENDING)

    def test_a_table_between_hands_has_no_game_to_play_open_in(self, herz_hand):
        herz_hand.played_out(HERZ_GAME)

        herz_hand.refused_act(TABLE_PLAY_OPEN_SUFFIX, herz_hand.at[FOREHAND], Refusal.NO_HAND)
