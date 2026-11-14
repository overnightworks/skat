from contextlib import contextmanager

from skat.engine.deal import Deal, Position
from skat.web.declaring import (
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
    AnnouncementToken,
    GameToken,
)
from tests.support.payload_cards import CARDS_BY_SEAT, wire_cards
from tests.web.support.playing import card_body, cards, game_of
from tests.web.support.skat import streams_of

# Seats: the declarer (middlehand) sits in seat 1, rearhand in seat 2, forehand in seat 3.
SEAT = {Position.MIDDLEHAND: 1, Position.REARHAND: 2, Position.FOREHAND: 3}

# Clubs and spades are the declarer's own: forehand and rearhand take the first two tricks, so a Null game runs on.
NULL_DEAL = Deal(
    forehand=cards("CT CQ CA ST SQ SA HT HQ D8 DT"),
    middlehand=cards("C7 C8 C9 S7 S8 S9 H7 H8 H9 D7"),
    rearhand=cards("CJ CK SJ SK HJ HK HA D9 DJ DQ"),
    skat=cards("DA DK"),
)
# The opponents took 10 + 2 and 4 + 3 points, so the declarer holds 120 - 19 = 101.
NULL_TWO_TRICKS = game_of("CT C7 CJ / CK CQ C8")
# Forehand leads an ace, and the partner adds a ten each time: three tricks of 11 + 10 + 0 = 21 points. The declarer
# holds the Spade Jack and not the Kreuz Jack, so Herz is played "ohne 1".
HEAVY_DEAL = Deal(
    forehand=cards("CA CJ SA DA HA HK HQ H9 H8 CK"),
    middlehand=cards("C7 C8 C9 S7 S8 S9 SJ H7 D7 D8"),
    rearhand=cards("CT CQ ST SK SQ HJ HT DT DJ DQ"),
    skat=cards("D9 DK"),
)
HEAVY_TWO_TRICKS = game_of("CA C7 CT / SA S7 ST")
HEAVY_THREE_TRICKS = game_of("CA C7 CT / SA S7 ST / DA D7 DT")


def playing_as(table, headers):
    answer = table.read_as(headers)
    assert answer.status_code == 200, answer.text
    return answer.json()["hand"]["playing"]


@contextmanager
def everyones_streams(table):
    """One open stream per viewer, the watcher first: each as (position or None for the watcher, decoded messages)."""
    viewers = [(None, table.watcher), *table.at.items()]
    with streams_of(table.skat, table.table_id, [(headers, None) for _, headers in viewers]) as streams:
        yield [(position, stream) for (position, _), stream in zip(viewers, streams, strict=True)]


def own_cards_of(position):
    """The cards a viewer's frame may carry before any card is played: his own hand, none for the watcher."""
    return set() if position is None else wire_cards(CARDS_BY_SEAT[SEAT[position]])


def declared_herz_at_22(table):
    """Herz played from the skat, declared below the bid: its simple value (1 + 1) * 10 = 20 is under 22."""
    table.middlehand_wins(22)
    for suffix, body in (
        (TABLE_DECLARING_TAKE_SUFFIX, None),
        (TABLE_DECLARING_PUT_BACK_SUFFIX, {"cards": [card_body(each) for each in cards("D9 DK")]}),
        (
            TABLE_DECLARING_DECLARE_SUFFIX,
            {"game": GameToken.HERZ, "hand": False, "ouvert": False, "announcement": AnnouncementToken.NONE},
        ),
    ):
        answer = table.act(suffix, body=body)
        assert answer.status_code == 200, answer.text
