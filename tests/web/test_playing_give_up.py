import pytest

from skat.engine.deal import Position
from skat.engine.tricks import ALL_POINTS
from skat.table.records import Refusal
from skat.web.declaring import GameToken
from skat.web.playing import TABLE_GIVE_UP_SUFFIX
from skat.web.tables import AnnouncementToken
from tests.support.payload_cards import cards_in_text
from tests.web.support.playing import DECLARER_SEAT, Table, card, cards, ending_of, points_of_cards
from tests.web.support.skat import streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
# Middlehand declares; the known deal's first trick is S7 S9 D7, which he takes with S9 and leads the next.
FIRST_TRICK = cards("S7 S9 D7")
HERZ_HAND_LOST_AT_30 = {
    "won": False,
    "game_value": 30,
    "settled_value": 30,
    "score": -60,
    "multiplier": 3,
    "list_bonus": -50,
    "announcement_missed": False,
}


@pytest.fixture
def table(skat):
    return Table(skat)


@pytest.fixture
def herz_hand(table):
    table.declared_hand_game()
    return table


def give_up(table, headers=None, *, body=None):
    return table.act(TABLE_GIVE_UP_SUFFIX, headers, body=body)


class TestTheDeclarerGivesUp:
    def test_with_ten_cards_the_game_is_lost_at_once_and_the_hand_ends(self, herz_hand):
        answer = give_up(herz_hand)

        assert answer.status_code == 200, answer.text
        assert herz_hand.record.hand is None
        assert len(herz_hand.record.game_list) == 1
        result = answer.json()["result"]
        assert {key: result[key] for key in HERZ_HAND_LOST_AT_30} == HERZ_HAND_LOST_AT_30

    def test_with_nine_cards_after_a_trick_the_game_is_given_up_without_consent(self, herz_hand):
        herz_hand.played_out(FIRST_TRICK)

        assert give_up(herz_hand).status_code == 200

    def test_the_declarers_points_are_those_of_his_completed_tricks_and_the_opponents_hold_the_rest(self, herz_hand):
        herz_hand.played_out(FIRST_TRICK)

        result = give_up(herz_hand).json()["result"]

        assert result["declarer_points"] == points_of_cards(FIRST_TRICK)
        assert result["opponents_points"] == ALL_POINTS - points_of_cards(FIRST_TRICK)

    def test_off_turn_mid_trick_the_open_trick_counts_nothing_for_the_declarer(self, table):
        table.declared_hand_game()
        table.accepted(card("CA"))
        table.accepted(card("SA"))

        answer = give_up(table)

        assert answer.status_code == 200, answer.text
        result = answer.json()["result"]
        assert result["declarer_points"] == 0
        assert result["opponents_points"] == ALL_POINTS

    def test_the_skat_never_shows_in_the_points(self, herz_hand):
        result = give_up(herz_hand).json()["result"]

        assert result["declarer_points"] == 0

    def test_the_entry_is_stored_lost_and_the_gains_follow(self, herz_hand):
        result = give_up(herz_hand).json()["result"]

        assert herz_hand.result() == result
        assert result["won"] is False
        assert [gain["won"] for gain in result["gains"]] == [False, True, True]
        assert result["gains"][0]["gain"] < 0 < result["gains"][1]["gain"]

    @pytest.mark.parametrize(
        ("changes", "levels", "multiplier", "announcement_missed"),
        [
            pytest.param({"announcement": AnnouncementToken.NONE}, ["spiel", "hand"], 3, False, id="not-announced"),
            pytest.param(
                {"announcement": AnnouncementToken.SCHNEIDER},
                ["spiel", "hand", "schneider", "schneider_announced"],
                5,
                True,
                id="schneider-announced",
            ),
            pytest.param(
                {"announcement": AnnouncementToken.SCHNEIDER, "bid": 60},
                ["spiel", "hand", "schneider", "schneider_announced"],
                5,
                False,
                id="schneider-announced-and-overbid",
            ),
        ],
    )
    def test_only_the_levels_announced_are_suffered(self, table, changes, levels, multiplier, announcement_missed):
        table.declared_hand_game(**changes)

        result = give_up(table).json()["result"]

        assert (result["levels"], result["multiplier"], result["list_bonus"], result["announcement_missed"]) == (
            levels,
            multiplier,
            -50,
            announcement_missed,
        )

    def test_a_bid_over_the_value_is_overbid_and_settled_at_the_next_multiple(self, table):
        table.declared_hand_game(bid=33)

        result = give_up(table).json()["result"]

        assert {key: result[key] for key in ("overbid", "game_value", "settled_value", "score")} == {
            "overbid": True,
            "game_value": 30,
            "settled_value": 40,
            "score": -80,
        }

    @pytest.mark.parametrize(
        ("ouvert", "value", "score"),
        [pytest.param(False, 35, -70, id="null-hand"), pytest.param(True, 59, -118, id="null-hand-ouvert")],
    )
    def test_a_null_is_lost_at_its_fixed_value_without_matadors(self, table, ouvert, value, score):
        table.declared_hand_game(GameToken.NULL, ouvert=ouvert)

        result = give_up(table).json()["result"]

        assert (result["won"], result["matadors"], result["game_value"], result["score"]) == (
            False,
            None,
            value,
            score,
        )

    def test_an_ouvert_declarers_open_cards_go_with_the_hand(self, table):
        table.declared_grand_ouvert()
        table.accepted(card("S7"))

        give_up(table)

        for headers in (table.watcher, *table.at.values()):
            assert cards_in_text(table.read_as(headers).text) == set()


class TestTheEnding:
    @pytest.fixture(params=[0, 1], ids=["ten-cards", "nine-cards"])
    def given_up(self, request, herz_hand):
        if request.param:
            herz_hand.played_out(FIRST_TRICK)
        return give_up(herz_hand)

    def test_the_answer_and_every_chair_and_the_watcher_read_the_declarer_as_the_seat_that_gave_up(
        self, herz_hand, given_up
    ):
        assert ending_of(given_up.json()["result"]) == ("given-up", DECLARER_SEAT)
        assert herz_hand.endings_in_every_view() == {("given-up", DECLARER_SEAT)}

    def test_a_retried_give_up_answers_the_same_two_fields_and_writes_one_entry(self, herz_hand):
        body = {"command_id": "command-give-up", "version": herz_hand.record.version}
        first = give_up(herz_hand, body=body)

        again = give_up(herz_hand, body=body)

        assert ending_of(again.json()["result"]) == ending_of(first.json()["result"]) == ("given-up", DECLARER_SEAT)
        assert len(herz_hand.record.game_list) == 1

    def test_the_stream_of_a_watcher_carries_the_two_fields(self, herz_hand):
        with streams_of(herz_hand.skat, herz_hand.table_id, [(herz_hand.watcher, None)]) as (watcher,):
            give_up(herz_hand)

            assert ending_of(next(watcher)["result"]) == ("given-up", DECLARER_SEAT)


class TestRefusals:
    @pytest.mark.parametrize("position", [FOREHAND, REARHAND], ids=lambda position: position.name)
    def test_an_opponent_is_not_the_declarer(self, herz_hand, position):
        herz_hand.refused_act(TABLE_GIVE_UP_SUFFIX, herz_hand.at[position], Refusal.NOT_DECLARER)
