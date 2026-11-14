import pytest

from skat.engine.deal import Position
from skat.web.declaration_tokens import AnnouncementToken, GameToken
from skat.web.playing import TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX, TABLE_SHORTEN_SUFFIX
from tests.support.payload_cards import CARDS_BY_SEAT, wire_cards
from tests.web.support.giving_up import (
    HEAVY_DEAL,
    HEAVY_THREE_TRICKS,
    HEAVY_TWO_TRICKS,
    NULL_DEAL,
    NULL_TWO_TRICKS,
    SEAT,
    declared_herz_at_22,
    playing_as,
)
from tests.web.support.playing import HERZ_GAME

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
NONE, SCHNEIDER, SCHWARZ = AnnouncementToken.NONE, AnnouncementToken.SCHNEIDER, AnnouncementToken.SCHWARZ
# After seven tricks the declarer holds 55 card points and the skat 15: 70 win the game, the opponents hold 50.
SEVEN_TRICKS = HERZ_GAME[:21]


def asked(claim=NONE, agreed=None):
    return {"asking_seat": SEAT[MIDDLEHAND], "claim": claim, "agreed_seat": agreed}


def shorten(table, *, claim=None, position=MIDDLEHAND, body=None):
    extra = {} if claim is None else {"claim": claim}
    return table.act(TABLE_SHORTEN_SUFFIX, table.at[position], body=extra | (body or {}))


def shortens(table, claim=None):
    answer = shorten(table, claim=claim)
    assert answer.status_code == 200, answer.text
    return answer


def answer_of(table, position, suffix):
    return table.act(suffix, table.at[position])


def says_yes(table, position):
    answer = answer_of(table, position, TABLE_GIVE_UP_AGREE_SUFFIX)
    assert answer.status_code == 200, answer.text
    return answer


def says_no(table, position):
    answer = answer_of(table, position, TABLE_GIVE_UP_DECLINE_SUFFIX)
    assert answer.status_code == 200, answer.text
    return answer


def both_say_yes(table):
    says_yes(table, FOREHAND)
    return says_yes(table, REARHAND).json()["result"]


def declaring_as(table, headers):
    return table.read_as(headers).json()["hand"]["declaring"]


def everyone(table, read):
    return [read(table, headers) for headers in (table.watcher, *table.at.values())]


def shortenings_read(table):
    return everyone(table, lambda each, headers: playing_as(each, headers)["shortening"])


def refusals_read(table):
    return everyone(table, lambda each, headers: playing_as(each, headers)["shortening_refused_seat"])


def open_cards_read(table):
    return everyone(
        table,
        lambda each, headers: {
            (each_card["suit"], each_card["rank"]) for each_card in declaring_as(each, headers)["open_cards"]
        },
    )


def declarers_cards():
    return wire_cards(CARDS_BY_SEAT[SEAT[MIDDLEHAND]])


def undecided_herz_at_22(table):
    table.with_deal(HEAVY_DEAL)
    declared_herz_at_22(table)


def herz_at_22_with_42_points_against(table):
    undecided_herz_at_22(table)
    table.played_out(HEAVY_TWO_TRICKS)


def herz_hand_with_63_points_against(table):
    table.with_deal(HEAVY_DEAL)
    table.declared_hand_game()
    table.played_out(HEAVY_THREE_TRICKS)


def herz_hand_won_by_tricks_and_skat(table):
    table.declared_hand_game()
    table.played_out(SEVEN_TRICKS)


def null_before_a_trick(table):
    table.with_deal(NULL_DEAL)
    table.declared_hand_game(GameToken.NULL)
    table.played_out(NULL_TWO_TRICKS)


SETTLED_GAMES = pytest.mark.parametrize(
    ("scene", "claim", "expected"),
    [
        pytest.param(
            herz_at_22_with_42_points_against,
            NONE,
            {"won": False, "opponents_points": 42, "declarer_points": 78},
            id="already-lost-stays-lost",
        ),
        pytest.param(
            herz_hand_with_63_points_against,
            NONE,
            {"won": False, "opponents_points": 63, "declarer_points": 57},
            id="already-lost-with-sixty-three",
        ),
        pytest.param(
            herz_hand_won_by_tricks_and_skat,
            NONE,
            {"won": True, "opponents_points": 50, "declarer_points": 70, "game_value": 30},
            id="already-won-keeps-its-real-result",
        ),
        pytest.param(
            herz_hand_won_by_tricks_and_skat,
            SCHNEIDER,
            {"won": True, "game_value": 40, "schneider": True},
            id="already-won-with-a-demand-counts-the-level",
        ),
        pytest.param(
            null_before_a_trick,
            NONE,
            {"won": True, "game_value": 35, "declarer_points": 101},
            id="null-without-a-demand",
        ),
    ],
)
