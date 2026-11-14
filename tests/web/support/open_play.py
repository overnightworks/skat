from skat.engine.deal import Position
from skat.web.playing import TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX, TABLE_PLAY_OPEN_SUFFIX
from tests.web.support.giving_up import SEAT, playing_as
from tests.web.support.playing import HERZ_GAME

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
# After nine tricks the declarer can take no trick of the tenth: the trump and the aces he lacks are the opponents'.
NINE_TRICKS = HERZ_GAME[:27]


def plays_open(table, position, *, body=None):
    return table.act(TABLE_PLAY_OPEN_SUFFIX, table.at[position], body=body)


def asked_to_play_open(table, position):
    answer = plays_open(table, position)
    assert answer.status_code == 200, answer.text
    return answer


def declarer_accepts(table):
    answer = table.act(TABLE_GIVE_UP_AGREE_SUFFIX, table.at[MIDDLEHAND])
    assert answer.status_code == 200, answer.text
    return answer


def declarer_plays_on(table):
    answer = table.act(TABLE_GIVE_UP_DECLINE_SUFFIX, table.at[MIDDLEHAND])
    assert answer.status_code == 200, answer.text
    return answer


def open_play_read(table):
    """The seat whose open play waits for the declarer, as the watcher and each chair read it."""
    return [playing_as(table, headers)["open_play_seat"] for headers in (table.watcher, *table.at.values())]


def waiting_for(position):
    return [SEAT[position]] * 4
